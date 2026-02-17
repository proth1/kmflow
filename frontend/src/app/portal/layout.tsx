export default function PortalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="border-b border-gray-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-3">
          <div className="flex items-center justify-between">
            <h1 className="text-lg font-semibold text-gray-900">
              KMFlow Client Portal
            </h1>
            <span className="text-sm text-gray-500">Read-Only Access</span>
          </div>
        </div>
      </nav>
      <main className="mx-auto max-w-7xl p-6">{children}</main>
    </div>
  );
}
