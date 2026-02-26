import * as React from "react"

interface AlertDialogContextValue {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const AlertDialogContext = React.createContext<AlertDialogContextValue>({
  open: false,
  onOpenChange: () => {},
})

function AlertDialog({ open = false, onOpenChange = () => {}, children }: {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  children: React.ReactNode
}) {
  return (
    <AlertDialogContext.Provider value={{ open, onOpenChange }}>
      {children}
    </AlertDialogContext.Provider>
  )
}

function AlertDialogContent({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const { open, onOpenChange } = React.useContext(AlertDialogContext)
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => onOpenChange(false)} />
      <div className={`relative z-10 w-full max-w-md rounded-xl border p-6 shadow-xl ${className}`} onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  )
}

function AlertDialogHeader({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`mb-4 ${className}`}>{children}</div>
}

function AlertDialogTitle({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <h2 className={`text-lg font-semibold ${className}`}>{children}</h2>
}

function AlertDialogDescription({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <p className={`mt-1 text-sm ${className}`}>{children}</p>
}

function AlertDialogFooter({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`flex justify-end gap-2 mt-6 ${className}`}>{children}</div>
}

function AlertDialogAction({ children, className = "", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-150 ${className}`} {...props}>
      {children}
    </button>
  )
}

function AlertDialogCancel({ children, className = "", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { onOpenChange } = React.useContext(AlertDialogContext)
  return (
    <button
      className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-150 ${className}`}
      onClick={() => onOpenChange(false)}
      {...props}
    >
      {children}
    </button>
  )
}

export {
  AlertDialog, AlertDialogContent, AlertDialogHeader,
  AlertDialogTitle, AlertDialogDescription, AlertDialogFooter,
  AlertDialogAction, AlertDialogCancel,
}
