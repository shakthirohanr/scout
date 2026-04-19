import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { DashboardShell } from "@/components/dashboard/dashboard-shell";
import { getChallengeCatalog } from "@/lib/backend";
import type { ChallengeCatalogItem } from "@/lib/types";

export const dynamic = "force-dynamic";

type ChallengePageProps = {
  params: Promise<{
    id: string;
  }>;
};

export async function generateMetadata({ params }: ChallengePageProps): Promise<Metadata> {
  const { id } = await params;
  const catalog = await getChallengeCatalog().catch(() => []);
  const challenge = catalog.find((item) => item.id === id) ?? null;

  return {
    title: challenge ? challenge.name : "CryptoAgent",
  };
}

export default async function ChallengePage({ params }: ChallengePageProps) {
  const { id } = await params;
  const catalog = await getChallengeCatalog().catch(() => [] as ChallengeCatalogItem[]);
  const challenge = catalog.find((item) => item.id === id) ?? null;

  if (!challenge) {
    notFound();
  }

  return (
    <div className="h-full overflow-hidden">
      <DashboardShell
        challengeId={id}
        challengeName={challenge.name}
        challengeState={challenge.state}
        catalogChallenges={catalog}
      />
    </div>
  );
}
