import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../ui/alert-dialog"

interface DeleteDialogProps {
  open: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function DeleteDialog({ open, onConfirm, onCancel }: DeleteDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={(v) => !v && onCancel()}>
      <AlertDialogContent className="bg-zinc-900 border-zinc-700">
        <AlertDialogHeader>
          <AlertDialogTitle className="text-white">Deletar conversa</AlertDialogTitle>
          <AlertDialogDescription className="text-zinc-400">
            Esta acao nao pode ser desfeita. O historico desta conversa sera removido permanentemente.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel} className="bg-zinc-800 border-zinc-700 text-zinc-300 hover:bg-zinc-700">
            Cancelar
          </AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm} className="bg-red-600 hover:bg-red-700 text-white">
            Deletar
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
