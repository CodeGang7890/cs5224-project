import { RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

import { useRandomNumber } from '../hooks/use-random-number'

/** Sample connection to configuration-service: shows a random number from the backend. */
export function RandomNumberCard() {
  const { data, isPending, isError, error, refetch, isFetching } = useRandomNumber()

  return (
    <Card className="max-w-sm">
      <CardHeader>
        <CardTitle>Random number</CardTitle>
        <CardDescription>From configuration-service</CardDescription>
        <CardAction>
          <Button
            variant="outline"
            size="icon"
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="Get a new number"
          >
            <RefreshCw className={cn(isFetching && 'animate-spin')} />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <Skeleton className="h-12 w-16" />
        ) : isError ? (
          <p className="text-destructive text-sm">
            Couldn't reach configuration-service: {error.message}
          </p>
        ) : (
          <p className="text-5xl font-bold tabular-nums">{data.value}</p>
        )}
      </CardContent>
    </Card>
  )
}
