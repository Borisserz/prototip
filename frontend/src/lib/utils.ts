import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Tailwind-aware className combiner used across the UI kit. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
