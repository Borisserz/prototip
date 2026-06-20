export const formatCompactNumber = (number: number) => {
  if (number === 0) return '0';
  if (Math.abs(number) >= 1_000_000_000) {
    return (number / 1_000_000_000).toFixed(1).replace(/\.0$/, '') + 'B';
  }
  if (Math.abs(number) >= 1_000_000) {
    return (number / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M';
  }
  if (Math.abs(number) >= 1_000) {
    return (number / 1_000).toFixed(1).replace(/\.0$/, '') + 'K';
  }
  return number.toString();
};
