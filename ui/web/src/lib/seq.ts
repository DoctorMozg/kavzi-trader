// The first event after a snapshot carries snapshot.seq + 1; anything else is a gap.
export function isNextSeq(last: number | null, seq: number): boolean {
  return last !== null && seq === last + 1;
}
