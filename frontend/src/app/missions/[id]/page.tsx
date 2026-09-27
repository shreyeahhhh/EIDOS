import { MissionWorkspace } from "@/components/mission/mission-workspace";

export default async function MissionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <MissionWorkspace missionId={id} />
    </div>
  );
}
