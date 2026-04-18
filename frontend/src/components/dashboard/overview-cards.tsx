import { Card, CardContent } from "@/components/ui/card";

type OverviewCardsProps = {
  totals: {
    sessions: number;
    running: number;
    solved: number;
    toolCalls: number;
    costUsd: number;
  };
};

const cards = [
  {
    label: "Tracked Sessions",
    key: "sessions",
    formatter: (value: number) => value.toString(),
  },
  {
    label: "Live Sessions",
    key: "running",
    formatter: (value: number) => value.toString(),
  },
  {
    label: "Solved Runs",
    key: "solved",
    formatter: (value: number) => value.toString(),
  },
  {
    label: "Tool Calls",
    key: "toolCalls",
    formatter: (value: number) => value.toLocaleString("en-US"),
  },
] as const;

export function OverviewCards({ totals }: OverviewCardsProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => {
        const value = totals[card.key];

        return (
          <Card key={card.key}>
            <CardContent className="flex items-start justify-between gap-4 p-4">
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">{card.label}</p>
                <p className="text-2xl font-semibold tracking-tight text-foreground">
                  {card.formatter(value)}
                </p>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
