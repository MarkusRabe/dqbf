//! `.frp` proof-trace reader. The on-disk format is a JSON array of
//! objects with fields `clause`, `rule`, `premises`, `pivot`, `part`,
//! `c3`, `fresh` (the last five optional / nullable). See
//! `core/proof_trace.py` for the canonical Python emitter — but this
//! parser shares no code with it.
//!
//! We deliberately use a hand-rolled JSON parser so the verifier has
//! no dependency that could change parsing semantics out from under
//! us. The grammar is small and the input is trusted to be a flat
//! array of flat objects with int/string/array-of-int values.

#[derive(Debug, Clone, PartialEq)]
pub struct Step {
    pub clause: Vec<i64>,
    pub rule: String,
    pub premises: Vec<usize>,
    pub pivot: Option<i64>,
    pub part: Option<Vec<i64>>,
    pub c3: Option<Vec<i64>>,
    pub fresh: Option<i64>,
}

#[derive(Debug)]
pub struct ParseErr(pub String);
impl std::fmt::Display for ParseErr {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "frp parse error: {}", self.0)
    }
}

pub fn load(path: &std::path::Path) -> Result<Vec<Step>, ParseErr> {
    let text = std::fs::read_to_string(path).map_err(|e| ParseErr(format!("read {path:?}: {e}")))?;
    parse(&text)
}

pub fn parse(text: &str) -> Result<Vec<Step>, ParseErr> {
    let mut p = P {
        s: text.as_bytes(),
        i: 0,
    };
    p.ws();
    let v = p.array(|p| p.step())?;
    p.ws();
    if p.i != p.s.len() {
        return Err(ParseErr(format!("trailing garbage at byte {}", p.i)));
    }
    Ok(v)
}

struct P<'a> {
    s: &'a [u8],
    i: usize,
}

impl<'a> P<'a> {
    fn ws(&mut self) {
        while self.i < self.s.len() && self.s[self.i].is_ascii_whitespace() {
            self.i += 1;
        }
    }
    fn expect(&mut self, c: u8) -> Result<(), ParseErr> {
        self.ws();
        if self.i < self.s.len() && self.s[self.i] == c {
            self.i += 1;
            Ok(())
        } else {
            Err(ParseErr(format!(
                "byte {}: expected '{}', got '{}'",
                self.i,
                c as char,
                self.s.get(self.i).copied().unwrap_or(0) as char
            )))
        }
    }
    fn peek(&mut self) -> u8 {
        self.ws();
        self.s.get(self.i).copied().unwrap_or(0)
    }
    fn array<T>(&mut self, mut item: impl FnMut(&mut Self) -> Result<T, ParseErr>) -> Result<Vec<T>, ParseErr> {
        self.expect(b'[')?;
        let mut out = Vec::new();
        self.ws();
        if self.peek() == b']' {
            self.i += 1;
            return Ok(out);
        }
        loop {
            out.push(item(self)?);
            self.ws();
            match self.peek() {
                b',' => {
                    self.i += 1;
                }
                b']' => {
                    self.i += 1;
                    return Ok(out);
                }
                c => return Err(ParseErr(format!("byte {}: expected ',' or ']', got '{}'", self.i, c as char))),
            }
        }
    }
    fn int(&mut self) -> Result<i64, ParseErr> {
        self.ws();
        let start = self.i;
        if self.peek() == b'-' {
            self.i += 1;
        }
        while self.i < self.s.len() && self.s[self.i].is_ascii_digit() {
            self.i += 1;
        }
        if start == self.i || (self.s[start] == b'-' && start + 1 == self.i) {
            return Err(ParseErr(format!("byte {start}: expected integer")));
        }
        std::str::from_utf8(&self.s[start..self.i])
            .unwrap()
            .parse()
            .map_err(|e| ParseErr(format!("byte {start}: bad int: {e}")))
    }
    fn string(&mut self) -> Result<String, ParseErr> {
        self.expect(b'"')?;
        let start = self.i;
        while self.i < self.s.len() && self.s[self.i] != b'"' {
            if self.s[self.i] == b'\\' {
                return Err(ParseErr("escape sequences in strings unsupported".into()));
            }
            self.i += 1;
        }
        if self.i >= self.s.len() {
            return Err(ParseErr("unterminated string".into()));
        }
        let out = std::str::from_utf8(&self.s[start..self.i])
            .map_err(|e| ParseErr(format!("string utf8: {e}")))?
            .to_string();
        self.i += 1;
        Ok(out)
    }
    fn null_or<T>(&mut self, f: impl FnOnce(&mut Self) -> Result<T, ParseErr>) -> Result<Option<T>, ParseErr> {
        self.ws();
        if self.s[self.i..].starts_with(b"null") {
            self.i += 4;
            Ok(None)
        } else {
            f(self).map(Some)
        }
    }
    fn step(&mut self) -> Result<Step, ParseErr> {
        self.expect(b'{')?;
        let mut clause: Option<Vec<i64>> = None;
        let mut rule: Option<String> = None;
        let mut premises: Vec<i64> = Vec::new();
        let mut pivot: Option<i64> = None;
        let mut part: Option<Vec<i64>> = None;
        let mut c3: Option<Vec<i64>> = None;
        let mut fresh: Option<i64> = None;
        self.ws();
        if self.peek() != b'}' {
            loop {
                let k = self.string()?;
                self.expect(b':')?;
                match k.as_str() {
                    "clause" => clause = self.null_or(|p| p.array(P::int))?,
                    "rule" => rule = self.null_or(P::string)?,
                    "premises" => premises = self.null_or(|p| p.array(P::int))?.unwrap_or_default(),
                    "pivot" => pivot = self.null_or(P::int)?,
                    "part" => part = self.null_or(|p| p.array(P::int))?,
                    "c3" => c3 = self.null_or(|p| p.array(P::int))?,
                    "fresh" => fresh = self.null_or(P::int)?,
                    _ => return Err(ParseErr(format!("unknown step field: {k}"))),
                }
                self.ws();
                match self.peek() {
                    b',' => {
                        self.i += 1;
                    }
                    b'}' => break,
                    c => return Err(ParseErr(format!("byte {}: expected ',' or '}}', got '{}'", self.i, c as char))),
                }
            }
        }
        self.expect(b'}')?;
        let prem: Vec<usize> = premises
            .into_iter()
            .map(|x| {
                if x < 0 {
                    Err(ParseErr(format!("negative premise index {x}")))
                } else {
                    Ok(x as usize)
                }
            })
            .collect::<Result<_, _>>()?;
        Ok(Step {
            clause: clause.ok_or_else(|| ParseErr("step missing 'clause'".into()))?,
            rule: rule.ok_or_else(|| ParseErr("step missing 'rule'".into()))?,
            premises: prem,
            pivot,
            part,
            c3,
            fresh,
        })
    }
}
