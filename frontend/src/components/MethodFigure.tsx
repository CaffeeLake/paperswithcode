/**
 * MethodFigure: 3-tier fallback chain (PLAN.md §4.3):
 *   1. Hand-drawn SVG keyed by canonical slug (this dictionary).
 *   2. method.image_url — covers ~95% of methods in live DB.
 *   3. GenericFig — shaped, captioned schematic.
 *
 * The SVG figures below are ported verbatim from the v2 design prototype.
 */

import React from "react";

import type { Method } from "@/lib/api";

// Vaswani-style box palette
const C = {
  pink: "#F8D7D9",
  pinkS: "#D9B0B3",
  yellow: "#FBEFC2",
  yellowS: "#C9B97D",
  orange: "#F8D7B3",
  orangeS: "#C99466",
  blue: "#CDE2EE",
  blueS: "#7FA4BA",
  purple: "#D4D2EA",
  purpleS: "#8E8AC0",
  green: "#CCE2C5",
  greenS: "#7DA475",
  ink: "#1A1814",
  faint: "#8E8678",
};

interface MFBoxProps {
  x: number;
  y: number;
  w: number;
  h: number;
  fill: string;
  stroke: string;
  label?: string;
  fontSize?: number;
  multiline?: [string, string];
}

const MFBox: React.FC<MFBoxProps> = ({ x, y, w, h, fill, stroke, label, fontSize = 10, multiline }) => (
  <g>
    <rect x={x} y={y} width={w} height={h} rx="3" ry="3" fill={fill} stroke={stroke} strokeWidth="1" />
    {multiline ? (
      <>
        <text x={x + w / 2} y={y + h / 2 - 2} fontSize={fontSize} fontFamily="var(--sans)" fill={C.ink} textAnchor="middle" dominantBaseline="middle">
          {multiline[0]}
        </text>
        <text x={x + w / 2} y={y + h / 2 + fontSize - 1} fontSize={fontSize} fontFamily="var(--sans)" fill={C.ink} textAnchor="middle" dominantBaseline="middle">
          {multiline[1]}
        </text>
      </>
    ) : (
      <text x={x + w / 2} y={y + h / 2} fontSize={fontSize} fontFamily="var(--sans)" fill={C.ink} textAnchor="middle" dominantBaseline="middle">
        {label}
      </text>
    )}
  </g>
);

const TransformerFig: React.FC = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: "block" }}>
    <text x="180" y="14" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Output Probabilities</text>
    <path d="M180 22 L180 32" stroke={C.ink} strokeWidth="1.2" />
    <MFBox x={150} y={32} w={60} h={20} fill={C.green} stroke={C.greenS} label="Softmax" />
    <path d="M180 52 L180 62" stroke={C.ink} strokeWidth="1.2" />
    <MFBox x={150} y={62} w={60} h={20} fill={C.purple} stroke={C.purpleS} label="Linear" />
    <path d="M180 82 L180 92" stroke={C.ink} strokeWidth="1.2" />
    <rect x="50" y="170" width="120" height="120" rx="4" fill="#EFEBE0" stroke={C.faint} strokeWidth="1" strokeDasharray="3 2" />
    <text x="20" y="232" fontSize="11" fontFamily="var(--serif)" fill={C.faint}>N×</text>
    <MFBox x={70} y={180} w={80} h={18} fill={C.yellow} stroke={C.yellowS} label="Add & Norm" />
    <MFBox x={70} y={200} w={80} h={28} fill={C.blue} stroke={C.blueS} multiline={["Feed", "Forward"]} />
    <MFBox x={70} y={236} w={80} h={18} fill={C.yellow} stroke={C.yellowS} label="Add & Norm" />
    <MFBox x={70} y={256} w={80} h={28} fill={C.orange} stroke={C.orangeS} multiline={["Multi-Head", "Attention"]} />
    <rect x="190" y="92" width="120" height="200" rx="4" fill="#EFEBE0" stroke={C.faint} strokeWidth="1" strokeDasharray="3 2" />
    <text x="320" y="195" fontSize="11" fontFamily="var(--serif)" fill={C.faint}>N×</text>
    <MFBox x={210} y={102} w={80} h={18} fill={C.yellow} stroke={C.yellowS} label="Add & Norm" />
    <MFBox x={210} y={122} w={80} h={28} fill={C.blue} stroke={C.blueS} multiline={["Feed", "Forward"]} />
    <MFBox x={210} y={158} w={80} h={18} fill={C.yellow} stroke={C.yellowS} label="Add & Norm" />
    <MFBox x={210} y={178} w={80} h={28} fill={C.orange} stroke={C.orangeS} multiline={["Multi-Head", "Attention"]} />
    <MFBox x={210} y={216} w={80} h={18} fill={C.yellow} stroke={C.yellowS} label="Add & Norm" />
    <MFBox x={210} y={236} w={80} h={28} fill={C.orange} stroke={C.orangeS} multiline={["Masked MH", "Attention"]} />
    <path d="M150 220 L195 192" stroke={C.ink} strokeWidth="1.2" fill="none" />
    <path d="M150 220 L195 200" stroke={C.ink} strokeWidth="1.2" fill="none" />
    <MFBox x={70} y={340} w={80} h={26} fill={C.pink} stroke={C.pinkS} multiline={["Input", "Embedding"]} />
    <MFBox x={210} y={340} w={80} h={26} fill={C.pink} stroke={C.pinkS} multiline={["Output", "Embedding"]} />
    <text x="110" y="395" fontSize="11" fontFamily="var(--serif)" fill={C.ink} textAnchor="middle">Inputs</text>
    <text x="250" y="395" fontSize="9" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Outputs (shifted right)</text>
  </svg>
);

const AttentionFig: React.FC = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: "block" }}>
    <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Scaled Dot-Product Attention</text>
    <MFBox x={140} y={40} w={80} h={26} fill={C.yellow} stroke={C.yellowS} label="MatMul" fontSize={11} />
    <path d="M180 66 L180 80" stroke={C.ink} />
    <MFBox x={140} y={80} w={80} h={26} fill={C.green} stroke={C.greenS} label="SoftMax" fontSize={11} />
    <path d="M180 106 L180 120" stroke={C.ink} />
    <MFBox x={140} y={120} w={80} h={26} fill={C.purple} stroke={C.purpleS} label="Mask (opt.)" fontSize={11} />
    <path d="M180 146 L180 160" stroke={C.ink} />
    <MFBox x={140} y={160} w={80} h={26} fill={C.blue} stroke={C.blueS} label="Scale ÷√dₖ" fontSize={11} />
    <path d="M180 186 L180 200" stroke={C.ink} />
    <MFBox x={140} y={200} w={80} h={26} fill={C.yellow} stroke={C.yellowS} label="MatMul" fontSize={11} />
    <path d="M156 226 L120 270" stroke={C.ink} />
    <path d="M180 226 L180 270" stroke={C.ink} />
    <path d="M204 226 L240 270" stroke={C.ink} />
    <MFBox x={100} y={270} w={40} h={24} fill={C.pink} stroke={C.pinkS} label="Q" fontSize={13} />
    <MFBox x={160} y={270} w={40} h={24} fill={C.pink} stroke={C.pinkS} label="K" fontSize={13} />
    <MFBox x={220} y={270} w={40} h={24} fill={C.pink} stroke={C.pinkS} label="V" fontSize={13} />
    <text x="180" y="330" fontSize="14" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">
      softmax(QK
      <tspan fontSize="9" baselineShift="super">⊤</tspan>
      {" / √d) V"}
    </text>
  </svg>
);

const DiffusionFig: React.FC = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: "block" }}>
    <text x="180" y="50" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Reverse process: pure noise → sample</text>
    {[0, 1, 2, 3, 4, 5].map((i) => {
      const x = 25 + i * 56;
      const noiseLevel = (5 - i) / 5;
      return (
        <g key={i}>
          <rect
            x={x}
            y={90}
            width={50}
            height={50}
            rx="3"
            fill={`oklch(${0.85 - noiseLevel * 0.1} 0.04 250)`}
            stroke={C.faint}
          />
          {noiseLevel < 0.4 && (
            <circle cx={x + 25} cy={115} r={12 - noiseLevel * 16} fill={C.orange} opacity={1 - noiseLevel * 1.5} />
          )}
        </g>
      );
    })}
    <rect x="60" y="240" width="240" height="120" rx="4" fill="#FFF9EE" stroke={C.faint} />
    <text x="180" y="260" fontSize="11" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">TRAINING OBJECTIVE</text>
    <text x="180" y="295" fontSize="14" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">
      L = E[‖ε − ε_θ(x_t, t)‖²]
    </text>
  </svg>
);

const GANFig: React.FC = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: "block" }}>
    <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Generator vs. Discriminator</text>
    <circle cx="50" cy="120" r="22" fill={C.purple} stroke={C.purpleS} />
    <text x="50" y="125" fontSize="14" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">z</text>
    <rect x="110" y="92" width="80" height="56" rx="3" fill={C.blue} stroke={C.blueS} />
    <text x="150" y="124" fontSize="14" fontFamily="var(--mono)" fill={C.ink} textAnchor="middle">G</text>
    <rect x="225" y="100" width="40" height="40" rx="3" fill={C.orange} stroke={C.orangeS} />
    <rect x="225" y="195" width="40" height="40" rx="3" fill={C.green} stroke={C.greenS} />
    <rect x="290" y="140" width="50" height="50" rx="3" fill={C.pink} stroke={C.pinkS} />
    <text x="315" y="170" fontSize="14" fontFamily="var(--mono)" fill={C.ink} textAnchor="middle">D</text>
  </svg>
);

const VAEFig: React.FC = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: "block" }}>
    <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Variational Autoencoder</text>
    <rect x="30" y="100" width="40" height="40" rx="3" fill={C.green} stroke={C.greenS} />
    <rect x="100" y="92" width="60" height="56" rx="3" fill={C.blue} stroke={C.blueS} />
    <text x="130" y="124" fontSize="11" fontFamily="var(--mono)" fill={C.ink} textAnchor="middle">Encoder</text>
    <circle cx="270" cy="120" r="14" fill={C.purple} stroke={C.purpleS} />
    <text x="270" y="124" fontSize="13" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">z</text>
    <rect x="100" y="200" width="60" height="56" rx="3" fill={C.orange} stroke={C.orangeS} />
    <text x="130" y="232" fontSize="11" fontFamily="var(--mono)" fill={C.ink} textAnchor="middle">Decoder</text>
    <rect x="30" y="210" width="40" height="40" rx="3" fill={C.pink} stroke={C.pinkS} />
  </svg>
);

const AGENT_SKILL_TREE_LINES: ReadonlyArray<readonly [string, string]> = [
  ["my-skill/", ""],
  ["├── SKILL.md", "# Required: metadata + instructions"],
  ["├── scripts/", "# Optional: executable code"],
  ["├── references/", "# Optional: documentation"],
  ["├── assets/", "# Optional: templates, resources"],
  ["└── ...", "# Any additional files or directories"],
];

const AgentSkillsFig: React.FC = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: "block" }}>
    <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">
      Skill package layout
    </text>
    <rect x="28" y="48" width="304" height="318" rx="8" fill="#FFFDF8" stroke={C.faint} strokeWidth="1" />
    {AGENT_SKILL_TREE_LINES.map(([entry, comment], index) => {
      const y = 92 + index * 44;
      return (
        <g key={entry}>
          <text x="44" y={y} fontSize="11" fontFamily="var(--mono)" fill={C.ink} dominantBaseline="middle">
            {entry}
          </text>
          {comment ? (
            <text x="138" y={y} fontSize="8.5" fontFamily="var(--mono)" fill={C.faint} dominantBaseline="middle">
              {comment}
            </text>
          ) : null}
        </g>
      );
    })}
  </svg>
);

const FIGURE_BY_SLUG: Record<string, React.FC> = {
  attention: AttentionFig,
  "self-attention": AttentionFig,
  ddpm: DiffusionFig,
  gan: GANFig,
  vae: VAEFig,
  "agent-skills": AgentSkillsFig,
};

const GenericFig: React.FC<{ method: Pick<Method, "name"> }> = ({ method }) => (
  <svg viewBox="0 0 360 420" width="100%" height="100%">
    <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">
      {method.name || "method"}
    </text>
    <MFBox x={80} y={70} w={200} h={50} fill={C.blue} stroke={C.blueS} label="Input" fontSize={12} />
    <path d="M180 120 L180 150" stroke={C.ink} />
    <MFBox x={80} y={150} w={200} h={70} fill={C.orange} stroke={C.orangeS} label={method.name || "transform"} fontSize={13} />
    <path d="M180 220 L180 250" stroke={C.ink} />
    <MFBox x={80} y={250} w={200} h={50} fill={C.purple} stroke={C.purpleS} label="Output" fontSize={12} />
  </svg>
);

interface MethodFigureProps {
  method: Pick<Method, "slug" | "name" | "image_url">;
}

export const MethodFigure: React.FC<MethodFigureProps> = ({ method }) => {
  const slug = (method.slug || "").toLowerCase();
  const FigFromDict = FIGURE_BY_SLUG[slug];
  if (FigFromDict) {
    return (
      <div className="method-figure-svg method-figure-svg--schematic">
        <FigFromDict />
      </div>
    );
  }
  if (method.image_url) {
    const sizeClass =
      slug === "transformer" ||
      slug === "gpt-4" ||
      slug === "gpt-4o" ||
      slug === "multi-head-attention"
        ? " method-figure-svg--compact"
        : slug === "rpn"
          ? " method-figure-svg--scaled-80"
          : "";
    return (
      <div
        className={`method-figure-svg method-figure-svg--image${sizeClass}`}
      >
        <img
          className="method-figure-img"
          src={method.image_url}
          alt={`${method.name} figure`}
        />
      </div>
    );
  }
  return (
    <div className="method-figure-svg method-figure-svg--schematic">
      <GenericFig method={method} />
    </div>
  );
};
