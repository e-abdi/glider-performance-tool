/* Tiny Excel-formula interpreter for the Slocum endurance model.
 *
 * The model ships as the workbook's own formula strings (see extract_endurance_model.py),
 * so this evaluates them rather than re-implementing the physics. It covers exactly the
 * subset those formulas use — operators + - * / ^ and = <> < > <= >=, ranges, and the
 * functions IF SUM AND OR MAX MIN ROUND ROUNDUP CEILING SQRT LEFT ATAN PI ABS — and
 * deliberately nothing else: an unknown name throws instead of quietly returning 0.
 *
 * Excel semantics worth naming, because getting them wrong is silent:
 *   - text comparison is case-insensitive, so "Ld" = "ld" is TRUE
 *   - an empty cell reads as 0 in arithmetic
 *   - SUM skips text rather than failing on it
 *
 * Works in Node and in the browser.
 */
(function (root) {
  "use strict";

  // ---------------------------------------------------------------- lexer
  const NUM = /^\d+(\.\d+)?([eE][-+]?\d+)?/;
  const REF = /^[A-Za-z_][A-Za-z0-9_]*!\$?[A-Z]{1,2}\$?\d+(:\$?[A-Z]{1,2}\$?\d+)?/;
  const NAME = /^[A-Za-z][A-Za-z0-9_.]*/;

  function tokenize(src) {
    const out = [];
    let i = 0;
    while (i < src.length) {
      const c = src[i];
      if (c === " " || c === "\t" || c === "\n" || c === "\r") { i++; continue; }
      if (c === '"') {
        let j = i + 1, s = "";
        while (j < src.length) {
          if (src[j] === '"' && src[j + 1] === '"') { s += '"'; j += 2; continue; }
          if (src[j] === '"') break;
          s += src[j++];
        }
        out.push({ t: "str", v: s });
        i = j + 1;
        continue;
      }
      let m = src.slice(i).match(REF);
      if (m) { out.push({ t: "ref", v: m[0].replace(/\$/g, "") }); i += m[0].length; continue; }
      m = src.slice(i).match(NUM);
      if (m) { out.push({ t: "num", v: parseFloat(m[0]) }); i += m[0].length; continue; }
      m = src.slice(i).match(NAME);
      if (m) { out.push({ t: "name", v: m[0].toUpperCase() }); i += m[0].length; continue; }
      const two = src.slice(i, i + 2);
      if (two === "<=" || two === ">=" || two === "<>") { out.push({ t: "op", v: two }); i += 2; continue; }
      if ("+-*/^=<>(),&".includes(c)) { out.push({ t: "op", v: c }); i++; continue; }
      throw new Error("unexpected character " + JSON.stringify(c) + " in: " + src);
    }
    return out;
  }

  // ---------------------------------------------------------------- parser
  // Precedence, loosest first: comparison < concat < +- < */ < ^ < unary < atom
  function parse(tokens) {
    let p = 0;
    const peek = () => tokens[p];
    const eat = (v) => {
      const t = tokens[p];
      if (!t || (v !== undefined && t.v !== v)) throw new Error("expected " + v + ", got " + JSON.stringify(t));
      p++;
      return t;
    };

    function comparison() {
      let left = concat();
      while (peek() && peek().t === "op" && ["=", "<>", "<", ">", "<=", ">="].includes(peek().v)) {
        const op = eat().v;
        left = { n: "bin", op, l: left, r: concat() };
      }
      return left;
    }
    function concat() {
      let left = additive();
      while (peek() && peek().t === "op" && peek().v === "&") {
        eat();
        left = { n: "bin", op: "&", l: left, r: additive() };
      }
      return left;
    }
    function additive() {
      let left = multiplicative();
      while (peek() && peek().t === "op" && (peek().v === "+" || peek().v === "-")) {
        const op = eat().v;
        left = { n: "bin", op, l: left, r: multiplicative() };
      }
      return left;
    }
    function multiplicative() {
      let left = power();
      while (peek() && peek().t === "op" && (peek().v === "*" || peek().v === "/")) {
        const op = eat().v;
        left = { n: "bin", op, l: left, r: power() };
      }
      return left;
    }
    function power() {
      const left = unary();
      if (peek() && peek().t === "op" && peek().v === "^") {
        eat();
        return { n: "bin", op: "^", l: left, r: power() };
      }
      return left;
    }
    function unary() {
      if (peek() && peek().t === "op" && (peek().v === "-" || peek().v === "+")) {
        const op = eat().v;
        return { n: "un", op, e: unary() };
      }
      return atom();
    }
    function atom() {
      const t = peek();
      if (!t) throw new Error("unexpected end of formula");
      if (t.t === "num") { eat(); return { n: "num", v: t.v }; }
      if (t.t === "str") { eat(); return { n: "str", v: t.v }; }
      if (t.t === "ref") { eat(); return { n: "ref", v: t.v }; }
      if (t.t === "name") {
        eat();
        if (t.v === "TRUE") return { n: "num", v: true };
        if (t.v === "FALSE") return { n: "num", v: false };
        eat("(");
        const args = [];
        // Excel allows omitted arguments, including a trailing one: SUM(A1,B1,)
        const arg = () => (peek() && (peek().v === "," || peek().v === ")")
          ? { n: "empty" } : comparison());
        if (peek() && peek().v !== ")") {
          args.push(arg());
          while (peek() && peek().v === ",") { eat(","); args.push(arg()); }
        }
        eat(")");
        return { n: "call", f: t.v, args };
      }
      if (t.t === "op" && t.v === "(") { eat("("); const e = comparison(); eat(")"); return e; }
      throw new Error("unexpected token " + JSON.stringify(t));
    }

    const ast = comparison();
    if (p !== tokens.length) throw new Error("trailing tokens in formula");
    return ast;
  }

  // ---------------------------------------------------------------- helpers
  const num = (v) => {
    if (v === null || v === undefined || v === "") return 0;
    if (typeof v === "boolean") return v ? 1 : 0;
    if (typeof v === "number") return v;
    const n = parseFloat(v);
    if (isNaN(n)) throw new Error("not a number: " + JSON.stringify(v));
    return n;
  };
  const isText = (v) => typeof v === "string";
  // Excel compares text without regard to case.
  const cmp = (a, b) => {
    if (isText(a) || isText(b)) {
      const x = isText(a) ? a.toUpperCase() : a, y = isText(b) ? b.toUpperCase() : b;
      if (isText(x) && isText(y)) return x < y ? -1 : x > y ? 1 : 0;
      return isText(x) ? 1 : -1;               // Excel sorts any text above any number
    }
    const x = num(a), y = num(b);
    return x < y ? -1 : x > y ? 1 : 0;
  };

  function colNum(c) { let n = 0; for (const ch of c) n = n * 26 + (ch.charCodeAt(0) - 64); return n; }
  function colName(n) { let s = ""; while (n) { const r = (n - 1) % 26; s = String.fromCharCode(65 + r) + s; n = (n - r - 1) / 26; } return s; }

  function expandRange(ref) {
    const [sheet, span] = ref.split("!");
    const [a, b] = span.split(":");
    if (!b) return [ref];
    const ma = a.match(/([A-Z]+)(\d+)/), mb = b.match(/([A-Z]+)(\d+)/);
    const c1 = colNum(ma[1]), c2 = colNum(mb[1]), r1 = +ma[2], r2 = +mb[2];
    const out = [];
    for (let c = Math.min(c1, c2); c <= Math.max(c1, c2); c++)
      for (let r = Math.min(r1, r2); r <= Math.max(r1, r2); r++)
        out.push(`${sheet}!${colName(c)}${r}`);
    return out;
  }

  // ---------------------------------------------------------------- engine
  function Model(cells) {
    this.cells = cells;
    this.ast = Object.create(null);
    this.reset();
  }

  Model.prototype.reset = function (overrides) {
    this.overrides = overrides || Object.create(null);
    this.memo = Object.create(null);
    this.visiting = Object.create(null);
  };

  Model.prototype.get = function (key) {
    if (key in this.overrides) return this.overrides[key];
    if (key in this.memo) return this.memo[key];
    if (this.visiting[key]) throw new Error("circular reference at " + key);

    let raw = this.cells[key];
    if (raw === undefined) return 0;                 // reference to a cell outside the model
    if (typeof raw !== "string") return (this.memo[key] = raw);
    // The extractor keeps the leading "=" on formulas, so anything else is literal text.
    // Never guess: a formula this interpreter cannot parse must throw, not silently
    // become the string it was written as.
    if (raw[0] !== "=") return (this.memo[key] = raw);

    let ast = this.ast[key];
    if (!ast) {
      try {
        ast = this.ast[key] = parse(tokenize(raw.slice(1)));
      } catch (e) {
        throw new Error(key + ": " + e.message);
      }
    }
    this.visiting[key] = true;
    let val;
    try {
      val = this.evaluate(ast);
    } finally {
      delete this.visiting[key];
    }
    return (this.memo[key] = val);
  };

  Model.prototype.evaluate = function (node) {
    switch (node.n) {
      case "num": case "str": return node.v;
      case "empty": return 0;                        // an omitted argument
      case "ref": {
        if (node.v.includes(":")) return expandRange(node.v).map((k) => this.get(k));
        return this.get(node.v);
      }
      case "un": {
        const v = num(this.evaluate(node.e));
        return node.op === "-" ? -v : v;
      }
      case "bin": {
        const l = this.evaluate(node.l), r = this.evaluate(node.r);
        switch (node.op) {
          case "+": return num(l) + num(r);
          case "-": return num(l) - num(r);
          case "*": return num(l) * num(r);
          case "/": {
            const d = num(r);
            if (d === 0) throw new Error("#DIV/0!");
            return num(l) / d;
          }
          case "^": return Math.pow(num(l), num(r));
          case "&": return String(l) + String(r);
          case "=": return cmp(l, r) === 0;
          case "<>": return cmp(l, r) !== 0;
          case "<": return cmp(l, r) < 0;
          case ">": return cmp(l, r) > 0;
          case "<=": return cmp(l, r) <= 0;
          case ">=": return cmp(l, r) >= 0;
        }
        throw new Error("unknown operator " + node.op);
      }
      case "call": {
        const self = this;
        const flat = () => {
          const out = [];
          node.args.forEach((a) => {
            const v = self.evaluate(a);
            Array.isArray(v) ? out.push.apply(out, v) : out.push(v);
          });
          return out;
        };
        switch (node.f) {
          // IF must not evaluate the branch it does not take: several branches in this
          // workbook divide by a cell that is zero in the other configuration.
          case "IF": {
            const test = this.evaluate(node.args[0]);
            const truthy = typeof test === "boolean" ? test : num(test) !== 0;
            if (truthy) return this.evaluate(node.args[1]);
            return node.args.length > 2 ? this.evaluate(node.args[2]) : false;
          }
          case "AND": return flat().every((v) => (typeof v === "boolean" ? v : num(v) !== 0));
          case "OR": return flat().some((v) => (typeof v === "boolean" ? v : num(v) !== 0));
          case "NOT": return !(num(this.evaluate(node.args[0])) !== 0);
          case "SUM": return flat().reduce((a, v) => a + (isText(v) ? 0 : num(v)), 0);
          case "MAX": return Math.max.apply(null, flat().filter((v) => !isText(v)).map(num));
          case "MIN": return Math.min.apply(null, flat().filter((v) => !isText(v)).map(num));
          case "ABS": return Math.abs(num(this.evaluate(node.args[0])));
          case "SQRT": return Math.sqrt(num(this.evaluate(node.args[0])));
          case "PI": return Math.PI;
          case "ATAN": return Math.atan(num(this.evaluate(node.args[0])));
          case "ROUND": {
            const x = num(this.evaluate(node.args[0]));
            const d = node.args.length > 1 ? num(this.evaluate(node.args[1])) : 0;
            const f = Math.pow(10, d);
            // Excel rounds half away from zero; JS Math.round rounds half up.
            return Math.sign(x) * Math.round(Math.abs(x) * f) / f;
          }
          case "ROUNDUP": {
            const x = num(this.evaluate(node.args[0]));
            const f = Math.pow(10, node.args.length > 1 ? num(this.evaluate(node.args[1])) : 0);
            return Math.sign(x) * Math.ceil(Math.abs(x) * f) / f;
          }
          case "CEILING": {
            const x = num(this.evaluate(node.args[0]));
            const s = num(this.evaluate(node.args[1]));
            if (s === 0) return 0;
            return Math.ceil(x / s) * s;
          }
          case "LEFT": {
            const s = String(this.evaluate(node.args[0]));
            const n = node.args.length > 1 ? num(this.evaluate(node.args[1])) : 1;
            return s.slice(0, n);
          }
        }
        throw new Error("unsupported function " + node.f + "()");
      }
    }
    throw new Error("bad node " + node.n);
  };

  /** Evaluate `keys` with `inputs` ({cellKey: value}) applied. */
  Model.prototype.compute = function (inputs, keys) {
    this.reset(inputs);
    const out = {};
    keys.forEach((k) => { out[k] = this.get(k); });
    return out;
  };

  const api = { Model, tokenize, parse };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.EnduranceEval = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
