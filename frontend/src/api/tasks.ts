import type { BaseModelRequest, OutputFile, TaskSummary } from "../models/shared";
import { requestJson } from "./http";

export interface TaskDeleteResult {
  task_id: string;
  deleted_task_record: boolean;
  deleted_output_dir: boolean;
}

export function createTaskClient<Request extends BaseModelRequest = BaseModelRequest, Metrics = Record<string, unknown>>(basePath: string) {
  return {
    list: () => requestJson<TaskSummary<Request, Metrics>[]>(basePath),
    create: (payload: Request) => requestJson<TaskSummary<Request, Metrics>>(basePath, { method: "POST", body: JSON.stringify(payload) }),
    get: (taskId: string) => requestJson<TaskSummary<Request, Metrics>>(`${basePath}/${taskId}`),
    metrics: (taskId: string) => requestJson<Metrics>(`${basePath}/${taskId}/metrics`),
    outputs: (taskId: string) => requestJson<OutputFile[]>(`${basePath}/${taskId}/outputs`),
    delete: (taskId: string) => requestJson<TaskDeleteResult>(`${basePath}/${taskId}`, { method: "DELETE" })
  };
}
