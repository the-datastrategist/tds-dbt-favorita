import { BrowserRouter, HashRouter } from "react-router-dom";
import { AppProviders } from "./providers";
import { AppRoutes } from "./routes";

export const App = () => {
  const Router = import.meta.env.MODE === "pages" ? HashRouter : BrowserRouter;

  return (
    <AppProviders>
      <Router
        basename={
          import.meta.env.MODE === "pages"
            ? undefined
            : import.meta.env.BASE_URL
        }
      >
        <AppRoutes />
      </Router>
    </AppProviders>
  );
};
