/**
 * Chances in words. The site puts "about 7 in 10" beside a percentage, so the
 * wording has to stay true to the number at every band edge.
 */
import { describe, expect, it } from "vitest";
import { chanceInWords, shownPodium } from "../src/lib/format";

describe("chanceInWords", () => {
  it("rounds to tenths for anything from about one in ten", () => {
    expect(chanceInWords(0.693)).toBe("about 7 in 10");
    expect(chanceInWords(0.28)).toBe("about 3 in 10");
    expect(chanceInWords(0.1)).toBe("about 1 in 10");
  });

  it("switches to one-in-N below one in ten", () => {
    expect(chanceInWords(0.05)).toBe("about 1 in 20");
    expect(chanceInWords(0.037)).toBe("about 1 in 27");
    expect(chanceInWords(0.01)).toBe("about 1 in 100");
  });

  it("never claims certainty, or ten in ten", () => {
    expect(chanceInWords(0.97)).toBe("more than 9 in 10");
    expect(chanceInWords(0.94)).toBe("about 9 in 10");
  });

  it("says plainly when the chance is tiny or nil", () => {
    expect(chanceInWords(0.004)).toBe("less than 1 in 100");
    expect(chanceInWords(0)).toBe("next to none");
  });

  it("uses 1 in N just below the tenths band", () => {
    // 0.094 rounds to 0.9 tenths: below the tenths band, it must read as 1 in N.
    expect(chanceInWords(0.094)).toBe("about 1 in 11");
  });
});

describe("shownPodium", () => {
  it("shows the tested podium chance where there is one, and the simulated one otherwise", () => {
    expect(shownPodium({ p_podium: 0.9, p_podium_model: 0.6 })).toBe(0.6);
    expect(shownPodium({ p_podium: 0.9 })).toBe(0.9);
  });
});
