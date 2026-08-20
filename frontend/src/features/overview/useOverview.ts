import { useQuery } from "@tanstack/react-query";
import { createDataSource } from "../../data";

const dataSource = createDataSource();

export const useOverview = () =>
  useQuery({
    queryKey: ["platform-overview"],
    queryFn: async () => {
      const options = await dataSource.getLeaderboardOptions();
      const segmentId = options.segments[0]?.id ?? "all";
      const results = await Promise.all(
        options.horizons.map((horizon) =>
          dataSource.getLeaderboard({ horizon, segmentId }),
        ),
      );
      return { options, results };
    },
  });
