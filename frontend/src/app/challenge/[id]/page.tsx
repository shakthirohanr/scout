import { notFound } from "next/navigation";

import { DashboardShell } from "@/components/dashboard/dashboard-shell";
import { buildChallengeItems } from "@/lib/challenges";
import { getChallengeCatalog } from "@/lib/backend";
import { getTraceSummaries } from "@/lib/logs";

export const dynamic = "force-dynamic";

type ChallengePageProps = {
  params: Promise<{
    id: string;
  }>;
};

export default async function ChallengePage({ params }: ChallengePageProps) {
  const { id } = await params;
  const [traces, catalog] = await Promise.all([
    getTraceSummaries(),
    getChallengeCatalog().catch(() => []),
  ]);
  const challengeItems = buildChallengeItems(traces, catalog);
  const selected = challengeItems.find((item) => item.id === id) ?? null;
  const challengeExists = Boolean(selected);

  if (!challengeExists) {
    notFound();
  }

  return (
    <DashboardShell
      initialTraces={traces}
      catalogChallenges={catalog}
      activeChallengeId={id}
      activeChallengeName={selected?.name ?? null}
    />
  );
}
