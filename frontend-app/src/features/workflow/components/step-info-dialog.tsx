import { ExternalLink } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

import { FLOW_NODE_META, type FlowNodeId } from '../steps'

interface StepInfoDialogProps {
  /** The block to describe; null closes the dialog. */
  nodeId: FlowNodeId | null
  /** Why customers can't reach the block right now, if they can't (e.g. no products yet). */
  unavailable?: string
  onClose: () => void
}

/** What a block of the flow diagram does, and where its data is managed (for blocks without settings). */
export function StepInfoDialog({ nodeId, unavailable, onClose }: StepInfoDialogProps) {
  const meta = nodeId ? FLOW_NODE_META[nodeId] : null
  return (
    <Dialog open={meta !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        {meta && (
          <>
            <DialogHeader>
              <DialogTitle>{meta.label}</DialogTitle>
              <DialogDescription>{meta.description}</DialogDescription>
            </DialogHeader>
            {unavailable && (
              <p className="bg-muted rounded-md px-3 py-2 text-sm">
                <strong>Not in use:</strong> {unavailable} Add one to switch this route on.
              </p>
            )}
            <p className="text-sm leading-relaxed">{meta.about}</p>
            <DialogFooter>
              {meta.link && (
                <Button variant="outline" asChild>
                  <Link to={meta.link.to}>
                    <ExternalLink /> {meta.link.label}
                  </Link>
                </Button>
              )}
              <Button onClick={onClose}>Close</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
