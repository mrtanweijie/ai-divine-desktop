import { createHashRouter, Navigate } from "react-router-dom";
import { AppLayout } from "@/layout/AppLayout";
import ChatPage from "@/pages/chat";
import { Providers } from "@/app/providers";

export const router = createHashRouter([
  {
    path: "/",
    element: (
      <Providers>
        <AppLayout />
      </Providers>
    ),
    children: [
      { index: true, element: <Navigate to="/chat" replace /> },
      { path: "chat", element: <ChatPage /> },
      { path: "*", element: <Navigate to="/chat" replace /> },
    ],
  },
]);
