import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  component: Index,
});

function Index() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <h1 className="text-4xl font-bold">habagou</h1>
      <p className="mt-4 text-lg text-gray-600">
        Learn to write Chinese characters by tracing them, stroke by stroke.
      </p>
    </main>
  );
}
