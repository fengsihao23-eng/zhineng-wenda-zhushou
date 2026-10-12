import { Navigate, useParams } from "react-router-dom";
import { TeacherWorkbench } from "./TeacherWorkbench";
import { StudentWorkbench } from "./StudentWorkbench";

type Kind = "teachers" | "students";

export function RosterWorkbench({ kind }: { kind: Kind }) {
  return kind === "teachers" ? <TeacherWorkbench /> : <StudentWorkbench />;
}

export function RosterTaskPage({ view }: { view: "import" | "history" | "batch" | "deletions" }) {
  const { kind = "teachers", batchId = "" } = useParams();
  if (kind !== "teachers" && kind !== "students") return <Navigate to="/admin/school" replace />;
  const prefix = kind === "teachers" ? "teacher" : "student";
  const values = new URLSearchParams({ tab: kind, [`${prefix}_view`]: view === "history" ? "records" : view === "deletions" && kind === "students" ? "records" : view });
  if (batchId) values.set(`${prefix}_batch`, batchId);
  return <Navigate to={`/admin/school?${values}`} replace />;
}
