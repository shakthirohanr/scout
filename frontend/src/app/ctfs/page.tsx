import { CtfBrowser } from "@/components/ctfs/ctf-browser";
import { getCTFs, getChallengeCatalog } from "@/lib/backend";
import type { ChallengeCatalogItem, CTFSourceSummary } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function CtfPage() {
  let ctfs: CTFSourceSummary[] = [];
  let catalog: ChallengeCatalogItem[] = [];

  try {
    catalog = await getChallengeCatalog();
    ctfs = await getCTFs();
  } catch {
    ctfs = [];
    catalog = [];
  }

  return <CtfBrowser initialCtfs={ctfs} initialChallenges={catalog} />;
}
