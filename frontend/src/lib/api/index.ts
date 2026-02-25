/**
 * Barrel export for the KMFlow API client.
 *
 * Re-exports everything from every domain module so that existing imports
 * from "@/lib/api" or "../lib/api" continue to resolve without any changes.
 */

export * from "./client";
export * from "./dashboard";
export * from "./tom";
export * from "./regulatory";
export * from "./monitoring";
export * from "./patterns";
export * from "./simulations";
export * from "./portal";
export * from "./graph";
export * from "./auth";
export * from "./camunda";
export * from "./governance";
export * from "./integrations";
export * from "./shelf-requests";
export * from "./metrics";
export * from "./annotations";
export * from "./taskmining";
