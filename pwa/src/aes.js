// AES-128 (FIPS-197) ECB, no padding.
//
// Web Bluetooth pages cannot use AES-ECB through WebCrypto (it only offers
// CBC/CTR/GCM/KW), and the alarm protocol is ECB, so we implement the block
// cipher here. Verified against the FIPS-197 vector and the real device
// captures in tests/vectors/golden.json.

const SBOX = new Uint8Array(256);
const INV_SBOX = new Uint8Array(256);
const RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36];

function gmul(a, b) {
  let p = 0;
  for (let i = 0; i < 8; i++) {
    if (b & 1) p ^= a;
    const hi = a & 0x80;
    a = (a << 1) & 0xff;
    if (hi) a ^= 0x1b;
    b >>= 1;
  }
  return p;
}

(function buildTables() {
  const inv = new Uint8Array(256);
  for (let i = 1; i < 256; i++) {
    for (let j = 1; j < 256; j++) {
      if (gmul(i, j) === 1) { inv[i] = j; break; }
    }
  }
  for (let i = 0; i < 256; i++) {
    let x = inv[i];
    let s = x;
    for (let k = 0; k < 4; k++) {
      x = ((x << 1) | (x >> 7)) & 0xff;
      s ^= x;
    }
    SBOX[i] = s ^ 0x63;
  }
  for (let i = 0; i < 256; i++) INV_SBOX[SBOX[i]] = i;
})();

function expandKey(key) {
  const w = [];
  for (let i = 0; i < 4; i++) w.push(Array.from(key.slice(4 * i, 4 * i + 4)));
  for (let i = 4; i < 44; i++) {
    let t = w[i - 1].slice();
    if (i % 4 === 0) {
      t = t.slice(1).concat(t[0]).map((b) => SBOX[b]);
      t[0] ^= RCON[i / 4 - 1];
    }
    w.push(w[i - 4].map((b, j) => b ^ t[j]));
  }
  return Uint8Array.from(w.flat());
}

function addRoundKey(s, rk, rnd) {
  for (let i = 0; i < 16; i++) s[i] ^= rk[rnd * 16 + i];
}
function subBytes(s) {
  for (let i = 0; i < 16; i++) s[i] = SBOX[s[i]];
}
function invSubBytes(s) {
  for (let i = 0; i < 16; i++) s[i] = INV_SBOX[s[i]];
}
function shiftRows(s) {
  const t = s.slice();
  for (let r = 1; r < 4; r++) for (let c = 0; c < 4; c++) s[4 * c + r] = t[4 * ((c + r) % 4) + r];
}
function invShiftRows(s) {
  const t = s.slice();
  for (let r = 1; r < 4; r++) for (let c = 0; c < 4; c++) s[4 * c + r] = t[4 * ((c - r + 4) % 4) + r];
}
function mixColumns(s) {
  for (let c = 0; c < 4; c++) {
    const a = [s[4 * c], s[4 * c + 1], s[4 * c + 2], s[4 * c + 3]];
    s[4 * c] = gmul(a[0], 2) ^ gmul(a[1], 3) ^ a[2] ^ a[3];
    s[4 * c + 1] = a[0] ^ gmul(a[1], 2) ^ gmul(a[2], 3) ^ a[3];
    s[4 * c + 2] = a[0] ^ a[1] ^ gmul(a[2], 2) ^ gmul(a[3], 3);
    s[4 * c + 3] = gmul(a[0], 3) ^ a[1] ^ a[2] ^ gmul(a[3], 2);
  }
}
function invMixColumns(s) {
  for (let c = 0; c < 4; c++) {
    const a = [s[4 * c], s[4 * c + 1], s[4 * c + 2], s[4 * c + 3]];
    s[4 * c] = gmul(a[0], 14) ^ gmul(a[1], 11) ^ gmul(a[2], 13) ^ gmul(a[3], 9);
    s[4 * c + 1] = gmul(a[0], 9) ^ gmul(a[1], 14) ^ gmul(a[2], 11) ^ gmul(a[3], 13);
    s[4 * c + 2] = gmul(a[0], 13) ^ gmul(a[1], 9) ^ gmul(a[2], 14) ^ gmul(a[3], 11);
    s[4 * c + 3] = gmul(a[0], 11) ^ gmul(a[1], 13) ^ gmul(a[2], 9) ^ gmul(a[3], 14);
  }
}

export function aes128EncryptBlock(block, key) {
  const rk = expandKey(key);
  const s = Array.from(block);
  addRoundKey(s, rk, 0);
  for (let rnd = 1; rnd < 10; rnd++) {
    subBytes(s);
    shiftRows(s);
    mixColumns(s);
    addRoundKey(s, rk, rnd);
  }
  subBytes(s);
  shiftRows(s);
  addRoundKey(s, rk, 10);
  return Uint8Array.from(s);
}

export function aes128DecryptBlock(block, key) {
  const rk = expandKey(key);
  const s = Array.from(block);
  addRoundKey(s, rk, 10);
  for (let rnd = 9; rnd > 0; rnd--) {
    invShiftRows(s);
    invSubBytes(s);
    addRoundKey(s, rk, rnd);
    invMixColumns(s);
  }
  invShiftRows(s);
  invSubBytes(s);
  addRoundKey(s, rk, 0);
  return Uint8Array.from(s);
}
