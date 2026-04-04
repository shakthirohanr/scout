import { ChallengeHome } from "@/components/home/challenge-home";
import { getChallengeCatalog } from "@/lib/backend";
import type { ChallengeCatalogItem } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function Home() {
  let challenges: ChallengeCatalogItem[] = [];
  try {
    challenges = await getChallengeCatalog();
  } catch {
    challenges = [];
  }
  return <ChallengeHome challenges={challenges} />;
}
