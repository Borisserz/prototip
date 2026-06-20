import * as React from "react"
import { cn } from "@/lib/utils"

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: "default" | "ghost" | "outline" | "secondary" | "destructive" | "link";
    size?: "default" | "sm" | "lg" | "icon";
  }

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", ...props }, ref) => {
    let variantClasses = "";
    if (variant === "default") {
      variantClasses = "bg-primary text-white shadow hover:bg-primary/90";
    } else if (variant === "ghost") {
      variantClasses = "hover:bg-slate-800/50 hover:text-white";
    } else if (variant === "outline") {
      variantClasses = "border border-slate-700 bg-transparent hover:bg-slate-800 hover:text-white";
    } else if (variant === "secondary") {
      variantClasses = "bg-slate-800 text-slate-100 hover:bg-slate-700";
    } else if (variant === "destructive") {
      variantClasses = "bg-rose-500 text-white hover:bg-rose-600 shadow-sm";
    } else if (variant === "link") {
      variantClasses = "text-primary underline-offset-4 hover:underline";
    }

    let sizeClasses = "";
    if (size === "default") {
      sizeClasses = "h-9 px-4 py-2";
    } else if (size === "sm") {
      sizeClasses = "h-8 rounded-md px-3 text-xs";
    } else if (size === "lg") {
      sizeClasses = "h-10 rounded-md px-8";
    } else if (size === "icon") {
      sizeClasses = "h-9 w-9";
    }

    return (
      <button
        className={cn(
          "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
          variantClasses,
          sizeClasses,
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button }
