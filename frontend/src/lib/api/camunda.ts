/**
 * Camunda / Process Management API: deployments, process definitions,
 * instances, tasks, and process start.
 */

import { apiGet, apiPost } from "./client";

// -- Types --------------------------------------------------------------------

export interface CamundaDeployment {
  id: string;
  name: string;
  deploymentTime: string;
  source: string | null;
  tenantId: string | null;
}

export interface ProcessDefinition {
  id: string;
  key: string;
  name: string | null;
  version: number;
  deploymentId: string;
  suspended: boolean;
  tenantId: string | null;
  category: string | null;
  description: string | null;
}

export interface ProcessInstance {
  id: string;
  definitionId: string;
  businessKey: string | null;
  suspended: boolean;
  ended: boolean;
  tenantId: string | null;
}

export interface CamundaTask {
  id: string;
  name: string;
  assignee: string | null;
  processDefinitionId: string;
  processInstanceId: string;
  created: string;
  taskDefinitionKey: string;
}

// -- API functions ------------------------------------------------------------

export async function fetchProcessDefinitions(): Promise<ProcessDefinition[]> {
  return apiGet<ProcessDefinition[]>("/api/v1/camunda/process-definitions");
}

export async function fetchDeployments(): Promise<CamundaDeployment[]> {
  return apiGet<CamundaDeployment[]>("/api/v1/camunda/deployments");
}

export async function fetchProcessInstances(
  active = true,
): Promise<ProcessInstance[]> {
  return apiGet<ProcessInstance[]>(
    `/api/v1/camunda/process-instances?active=${active}`,
  );
}

export async function fetchCamundaTasks(
  assignee?: string,
): Promise<CamundaTask[]> {
  const params = assignee ? `?assignee=${assignee}` : "";
  return apiGet<CamundaTask[]>(`/api/v1/camunda/tasks${params}`);
}

export async function startProcess(
  key: string,
  variables?: Record<string, string>,
): Promise<ProcessInstance> {
  return apiPost<ProcessInstance>(`/api/v1/camunda/process/${key}/start`, {
    variables: variables || null,
  });
}
