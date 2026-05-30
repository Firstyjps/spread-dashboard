const MINUS = "−";

const integerUSD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const decimalUSD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const integerNumber = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

const decimalNumber = (digits: number) =>
  new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

const decimalCache = new Map<number, Intl.NumberFormat>();
function fmt(digits: number) {
  let f = decimalCache.get(digits);
  if (!f) {
    f = decimalNumber(digits);
    decimalCache.set(digits, f);
  }
  return f;
}

function withSign(formatted: string, value: number, signed: boolean) {
  if (value < 0) return MINUS + formatted.replace(/^-/, "");
  return signed ? "+" + formatted : formatted;
}

export type FormatOptions = {
  decimals?: number;
  signed?: boolean;
};

export function formatUSD(value: number, opts: FormatOptions = {}) {
  const { decimals, signed = false } = opts;
  const abs = Math.abs(value);
  const f =
    decimals === undefined
      ? Number.isInteger(value)
        ? integerUSD
        : decimalUSD
      : new Intl.NumberFormat("en-US", {
          style: "currency",
          currency: "USD",
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        });
  const formatted = f.format(abs);
  return withSign(formatted, value, signed);
}

export function formatPercent(value: number, opts: FormatOptions = {}) {
  const { decimals = 2, signed = true } = opts;
  const abs = Math.abs(value);
  const formatted = fmt(decimals).format(abs) + "%";
  return withSign(formatted, value, signed);
}

export function formatNumber(value: number, opts: FormatOptions = {}) {
  const { decimals, signed = false } = opts;
  const abs = Math.abs(value);
  const formatted =
    decimals === undefined
      ? integerNumber.format(abs)
      : fmt(decimals).format(abs);
  return withSign(formatted, value, signed);
}
