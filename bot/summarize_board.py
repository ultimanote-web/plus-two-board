#!/usr/bin/env python3
"""
summarize_board.py — render a predictions file as markdown for the Action summary.

Lives in a file rather than a heredoc inside board.yml because a heredoc terminator
inside a YAML `run: |` block is indented, and bash only accepts it at column zero
(`<<-` strips tabs, not spaces). That silently broke the summary step.

    python3 bot/summarize_board.py predictions/2026-09-14.json
"""
import json, sys


def main():
    if len(sys.argv) < 2:
        print("usage: summarize_board.py <predictions/*.json>")
        return
    d = json.load(open(sys.argv[1]))
    print(f"## Board for {d['date']}\n")
    print(f"- field **{d['field']}**, selected **{d['selected']}**, "
          f"eligible but unranked **{d['eligible_unranked']}**")
    print(f"- snapshot `{d['snapshot']}`, de-bias applied: **{d.get('debias_applied')}**")
    if d.get("exclusions"):
        print(f"- manually excluded: {', '.join(d['exclusions'])}")
    print("\n| # | city | stamp | mult | tail | gap | sky |")
    print("|---|---|---|---|---|---|---|")
    for r in d["rows"][:10]:
        gap = f"{r['gap']:+.1f}" if r.get("gap") is not None else "&mdash;"
        rain, cloud = r.get("rain_mm"), r.get("cloud_pct")
        sky = "&mdash;" if rain is None else (
            "rain" if rain >= 2 else "showers" if rain >= 0.2
            else "cloudy" if (cloud or 0) >= 80 else "partly" if (cloud or 0) >= 40 else "clear")
        print(f"| {r['rank']} | {r['city']} | {r['stamp']} | {r['mult']:.2f}x | "
              f"{r['tail']*100:.1f}% | {gap} | {sky} |")
    print("\n_Rank is a research ordering. Only a `selected` stamp is a trade, and only "
          "when STATUS.md is not HALTED._")


if __name__ == "__main__":
    main()
