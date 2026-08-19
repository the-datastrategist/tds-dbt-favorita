import { useQuery } from "@tanstack/react-query";
import { createDataSource } from "../../data";

const dataSource = createDataSource();

export const useOverview = () =>
  useQuery({
    queryKey: ["platform-overview", "demo_all"],
    queryFn: async () => {
      const options = await dataSource.getLeaderboardOptions();
      const results = await Promise.all(
        options.horizons.map((horizon) =>
          dataSource.getLeaderboard({ horizon, segmentId: "demo_all" }),
        ),
      );
      return { options, results };
    },
  });
