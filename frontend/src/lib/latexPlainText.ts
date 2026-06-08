/**
 * Plain-text conversion for arXiv LaTeX titles (browser tab, not KaTeX UI).
 * Mirrors backend/utils/latex_text.py for SPA document.title updates.
 */

const LATEX_ACUTE: Record<string, string> = {
  a: 'á', e: 'é', i: 'í', o: 'ó', u: 'ú', y: 'ý',
  A: 'Á', E: 'É', I: 'Í', O: 'Ó', U: 'Ú', Y: 'Ý',
};
const LATEX_GRAVE: Record<string, string> = {
  a: 'à', e: 'è', i: 'ì', o: 'ò', u: 'ù',
  A: 'À', E: 'È', I: 'Ì', O: 'Ò', U: 'Ù',
};
const LATEX_CIRCUMFLEX: Record<string, string> = {
  a: 'â', e: 'ê', i: 'î', o: 'ô', u: 'û',
  A: 'Â', E: 'Ê', I: 'Î', O: 'Ô', U: 'Û',
};
const LATEX_UMLAUT: Record<string, string> = {
  a: 'ä', e: 'ë', i: 'ï', o: 'ö', u: 'ü', y: 'ÿ',
  A: 'Ä', E: 'Ë', I: 'Ï', O: 'Ö', U: 'Ü', Y: 'Ÿ',
};
const LATEX_ACCENT_BY_COMMAND: Record<string, Record<string, string>> = {
  "'": LATEX_ACUTE,
  '`': LATEX_GRAVE,
  '^': LATEX_CIRCUMFLEX,
  '"': LATEX_UMLAUT,
  '~': { n: 'ñ', N: 'Ñ' },
};
const LATEX_STANDALONE_COMMANDS: Record<string, string> = {
  ss: 'ß', ae: 'æ', AE: 'Æ', oe: 'œ', OE: 'Œ', o: 'ø', O: 'Ø', l: 'ł', L: 'Ł',
};

const LATEX_MATH_SYMBOLS: [string, string][] = [
  ['varphi', 'φ'], ['varepsilon', 'ε'], ['vartheta', 'ϑ'],
  ['Gamma', 'Γ'], ['Delta', 'Δ'], ['Theta', 'Θ'], ['Lambda', 'Λ'], ['Sigma', 'Σ'], ['Omega', 'Ω'],
  ['alpha', 'α'], ['beta', 'β'], ['gamma', 'γ'], ['delta', 'δ'], ['epsilon', 'ε'],
  ['zeta', 'ζ'], ['eta', 'η'], ['theta', 'θ'], ['kappa', 'κ'], ['lambda', 'λ'], ['mu', 'μ'],
  ['nu', 'ν'], ['xi', 'ξ'], ['pi', 'π'], ['rho', 'ρ'], ['sigma', 'σ'], ['tau', 'τ'],
  ['phi', 'φ'], ['chi', 'χ'], ['psi', 'ψ'], ['omega', 'ω'],
];

const BRACED_TEXT_COMMAND_RE = /\\(?:textbf|mathbf|emph|textit|textsl|texttt|color|textcolor)\{([^{}]*)\}/g;
const ACCENT_RE = /\\(['"`^~])([A-Za-z])/g;
const CEDILLA_RE = /\\c\{([cCsS])\}/g;
const STANDALONE_RE = new RegExp(
  `\\\\(${Object.keys(LATEX_STANDALONE_COMMANDS).join('|')})(?![A-Za-z])`,
  'g',
);
const DISPLAY_MATH_RE = /\$\$([^$]+)\$\$/g;
const INLINE_MATH_RE = /\$([^$]+)\$/g;
const MATH_COMMAND_RE = /\\([A-Za-z]+)/g;

function mathSegmentToPlain(segment: string): string {
  let plain = segment.trim();
  for (const [name, char] of LATEX_MATH_SYMBOLS) {
    plain = plain.replaceAll(`\\${name}`, char);
  }
  plain = plain.replace(MATH_COMMAND_RE, (_, cmd: string) => cmd);
  return plain.replaceAll('$', '');
}

function unwrapMathDelimiters(text: string): string {
  let plain = text.replace(DISPLAY_MATH_RE, (_, inner: string) => mathSegmentToPlain(inner));
  plain = plain.replace(INLINE_MATH_RE, (_, inner: string) => mathSegmentToPlain(inner));
  return plain.replaceAll('$', '');
}

export function latexToPlainText(text: string): string {
  if (!text) return text;

  let plain = text.replace(BRACED_TEXT_COMMAND_RE, '$1');
  plain = plain.replace(CEDILLA_RE, (_, letter: string) => ({ c: 'ç', C: 'Ç' })[letter] ?? _);
  plain = plain.replace(ACCENT_RE, (match, accent: string, letter: string) => {
    return LATEX_ACCENT_BY_COMMAND[accent]?.[letter] ?? match;
  });
  plain = plain.replace(STANDALONE_RE, (_, cmd: string) => LATEX_STANDALONE_COMMANDS[cmd] ?? _);
  plain = unwrapMathDelimiters(plain);
  return plain.replaceAll('~', '\u00a0');
}

const DEFAULT_SITE_SUFFIX = 'Papers with Code';

export function formatPageTitle(
  title: string,
  siteSuffix: string = DEFAULT_SITE_SUFFIX,
): string {
  const plain = latexToPlainText(title.trim()) || 'Paper';
  return `${plain} | ${siteSuffix}`;
}

export { DEFAULT_SITE_SUFFIX };
