import type { Metadata } from "next";
import Playground from '@/components/Playground';

export const metadata: Metadata = {
  title: "Playground | Verification",
  description: "Try the real V&V backend: score a trace, check governance, submit a pilot.",
};

export default function PlaygroundPage() {
  return <Playground />;
}
