import React from "react";

type LogoSize = "sm" | "lg";

interface LogoProps {
  size?: LogoSize;
}

const STROKES = [
  "M 4,50 C 8,35 18,15 32,6",
  "M 9,52 C 13,36 24,16 39,7",
  "M 14,53 C 19,37 30,17 45,8",
  "M 19,54 C 25,38 36,18 51,9",
  "M 24,55 C 30,39 42,19 56,10",
  "M 29,55 C 36,40 47,21 58,14",
  "M 33,54 C 40,41 51,24 58,20",
  "M 37,53 C 43,42 53,27 57,26",
  "M 40,52 C 45,43 53,31 56,32",
];

export default function Logo({ size = "sm" }: LogoProps) {
  const isLg = size === "lg";

  const svgHeight = isLg ? 48 : 28;
  const svgWidth = isLg ? 48 : 28;
  const textStyle: React.CSSProperties = {
    fontFamily: "'Inter', sans-serif",
    fontWeight: 600,
    color: "#2C1010",
    letterSpacing: "-0.01em",
    fontSize: isLg ? "2rem" : "1.1rem",
    lineHeight: 1,
  };

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: isLg ? "12px" : "7px",
      }}
    >
      <svg
        viewBox="0 0 62 60"
        width={svgWidth}
        height={svgHeight}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        {STROKES.map((d, i) => (
          <path
            key={i}
            d={d}
            stroke="#7BAD8A"
            strokeWidth="1.6"
            strokeLinecap="round"
            fill="none"
          />
        ))}
      </svg>
      <span style={textStyle}>confluex</span>
    </span>
  );
}
