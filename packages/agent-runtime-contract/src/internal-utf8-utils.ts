export const utf8ByteLengthUpTo = (value: string, limit = Number.MAX_SAFE_INTEGER): number => {
  let bytes = 0;
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    let increment: number;
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        increment = 4;
        index += 1;
      } else {
        increment = 3;
      }
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      increment = 3;
    } else if (codeUnit <= 0x7f) {
      increment = 1;
    } else if (codeUnit <= 0x7ff) {
      increment = 2;
    } else {
      increment = 3;
    }
    bytes += increment;
    if (bytes > limit) return limit + 1;
  }
  return bytes;
};

export const utf8ByteLengthAtMost = (value: string, limit: number): boolean =>
  utf8ByteLengthUpTo(value, limit) <= limit;
