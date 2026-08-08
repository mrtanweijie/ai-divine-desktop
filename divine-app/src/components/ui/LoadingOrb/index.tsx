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
  speed?: number;
}

export function LoadingOrb({
  state = "shaping",
  size = 20,
  speed,
}: LoadingOrbProps) {
  return <ThinkingOrb state={state} size={size} speed={speed} />;
}
