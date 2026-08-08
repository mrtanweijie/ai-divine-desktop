import { ThinkingOrb } from "thinking-orbs";

export type OrbState =
  | "working"
  | "searching"
  | "solving"
  | "listening"
  | "connecting"
  | "weaving"
  | "composing"
  | "breathing"
  | "shaping";

interface LoadingOrbProps {
  state?: OrbState;
  size?: 20 | 64;
}

export function LoadingOrb({ state = "shaping", size = 20 }: LoadingOrbProps) {
  return <ThinkingOrb state={state} size={size} />;
}
