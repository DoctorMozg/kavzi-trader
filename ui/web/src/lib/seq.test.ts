import { describe, expect, it } from "vitest";
import { isNextSeq } from "@/lib/seq";

describe("isNextSeq", () => {
  it("accepts only the consecutive seq", () => {
    expect(isNextSeq(10, 11)).toBe(true);
    expect(isNextSeq(10, 12)).toBe(false);
    expect(isNextSeq(10, 10)).toBe(false);
    expect(isNextSeq(10, 9)).toBe(false);
  });

  it("rejects events before any snapshot", () => {
    expect(isNextSeq(null, 1)).toBe(false);
  });
});
