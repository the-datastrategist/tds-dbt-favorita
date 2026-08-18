import { BrowserRouter } from "react-router-dom";
import { AppProviders } from "./providers";
import { AppRoutes } from "./routes";

export const App = () => (
  <AppProviders>
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <AppRoutes />
    </BrowserRouter>
  </AppProviders>
);
