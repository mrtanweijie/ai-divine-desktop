import { createHashRouter, Navigate } from "react-router";
import { AppLayout } from "@/layout/AppLayout";
import ChatPage from "@/pages/chat";
import { Providers } from "@/app/Providers";
import { StartupGate } from "@/components/StartupGate";

type HashRouterOptions = NonNullable<
  Parameters<typeof createHashRouter>[1]
>;

const routerOptions = {
  future: {
    v7_startTransition: true,
  },
} as unknown as HashRouterOptions;

export const router = createHashRouter(
  [
    {
      path: "/",
      element: (
        <Providers>
          <StartupGate>
            <AppLayout />
          </StartupGate>
        </Providers>
      ),
      children: [
        { index: true, element: <Navigate to="/chat" replace /> },
        { path: "chat", element: <ChatPage /> },
        { path: "*", element: <Navigate to="/chat" replace /> },
      ],
    },
  ],
  routerOptions
);
