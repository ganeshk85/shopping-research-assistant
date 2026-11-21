import type { Metadata } from "next";

import { ResearchApp } from "@/components/research/research-app";

export const metadata: Metadata = { title: "Research" };

export default function ResearchPage() {
  return <ResearchApp />;
}
