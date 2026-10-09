import { useEffect, useState } from 'react'
import { CalendarDays, Pencil, Plus, Trash2 } from 'lucide-react'

import { PaginationControls } from '@/components/common/pagination-controls'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { usePageParam } from '@/hooks/use-page-param'

import { describeWeek, openHours } from '../availability'
import { SERVICES_PAGE_SIZE, useAvailabilities, useServices } from '../hooks/use-services'
import type { Service, WeeklyAvailability } from '../types'
import { formatMinutes } from '../validation'
import { AvailabilityEditorDialog } from './availability-editor-dialog'
import { DeleteAvailabilityDialog, DeleteServiceDialog } from './delete-dialogs'
import { ServiceFormDialog } from './service-form-dialog'

const priceFormat = new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

type FormState<T> = { open: false } | { open: true; item?: T }

/** The Service tab: services (what customers book) and weekly availabilities (when they can). */
export function ServiceManager() {
  const [actionError, setActionError] = useState<string | null>(null)
  return (
    <div className="grid gap-10">
      {actionError && (
        <p role="alert" className="text-destructive text-sm">
          {actionError}
        </p>
      )}
      <ServicesSection onError={setActionError} />
      <AvailabilitiesSection onError={setActionError} />
    </div>
  )
}

function ServicesSection({ onError }: { onError: (message: string | null) => void }) {
  const [page, setPage] = usePageParam()
  const { data, isPending, isError, error, refetch, isPlaceholderData } = useServices(page)
  const availabilities = useAvailabilities()
  const [form, setForm] = useState<FormState<Service>>({ open: false })
  const [deleting, setDeleting] = useState<Service | null>(null)
  const names = new Map((availabilities.data?.results ?? []).map((a) => [a.id, a.name]))

  useEffect(() => {
    if (isError && error.status === 404 && page > 1) setPage(page - 1)
  }, [isError, error, page, setPage])

  return (
    <section className="grid gap-4" aria-labelledby="services-heading">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 id="services-heading" className="text-lg font-semibold">
            Services
          </h2>
          <p className="text-muted-foreground text-sm">
            {data ? `${data.count} service${data.count === 1 ? '' : 's'} customers can book a time for` : ' '}
          </p>
        </div>
        <Button onClick={() => setForm({ open: true })}>
          <Plus /> Add service
        </Button>
      </div>

      {isPending ? (
        <div className="grid gap-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : isError && !data ? (
        <div className="border-destructive/50 flex flex-col items-start gap-3 rounded-lg border p-4">
          <p className="text-destructive text-sm">Couldn't load services: {error.message}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : data.results.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-10 text-center">
          <p className="font-medium">No services yet</p>
          <p className="text-muted-foreground text-sm">
            Add a service (e.g. a photoshoot), and link it to the weekly availability of whoever does it.
          </p>
          <Button variant="outline" onClick={() => setForm({ open: true })}>
            <Plus /> Add service
          </Button>
        </div>
      ) : (
        <div className={isPlaceholderData ? 'opacity-60 transition-opacity' : undefined}>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="min-w-48">Name</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Buffer</TableHead>
                  <TableHead>Who can do it</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-24 text-right">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.results.map((service) => (
                  <TableRow key={service.id}>
                    <TableCell className="max-w-80 whitespace-normal">
                      <div className="font-medium">{service.name}</div>
                      {service.description && (
                        <div className="text-muted-foreground line-clamp-1 text-xs">{service.description}</div>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{priceFormat.format(Number(service.price))}</TableCell>
                    <TableCell className="whitespace-nowrap">{formatMinutes(service.duration_minutes)}</TableCell>
                    <TableCell className="text-muted-foreground whitespace-nowrap">
                      {service.buffer_minutes ? formatMinutes(service.buffer_minutes) : '—'}
                    </TableCell>
                    <TableCell className="max-w-60 whitespace-normal">
                      {service.weekly_availability.length === 0 ? (
                        <span className="text-destructive text-xs">No one: can't be booked</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {service.weekly_availability.map((id) => (
                            <Badge key={id} variant="outline">
                              {names.get(id) ?? `#${id}`}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant={service.is_active ? 'secondary' : 'outline'}>
                        {service.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon" aria-label={`Edit ${service.name}`} onClick={() => setForm({ open: true, item: service })}>
                        <Pencil />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Delete ${service.name}`}
                        onClick={() => {
                          onError(null)
                          setDeleting(service)
                        }}
                      >
                        <Trash2 className="text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="mt-4">
            <PaginationControls page={page} pageSize={SERVICES_PAGE_SIZE} count={data.count} onPageChange={setPage} disabled={isPlaceholderData} />
          </div>
        </div>
      )}

      <ServiceFormDialog
        open={form.open}
        onOpenChange={(open) => !open && setForm({ open: false })}
        service={form.open ? form.item : undefined}
      />
      <DeleteServiceDialog item={deleting} onOpenChange={(open) => !open && setDeleting(null)} onError={onError} />
    </section>
  )
}

function AvailabilitiesSection({ onError }: { onError: (message: string | null) => void }) {
  const { data, isPending, isError, error, refetch } = useAvailabilities()
  const services = useServices(1)
  const [form, setForm] = useState<FormState<WeeklyAvailability>>({ open: false })
  const [deleting, setDeleting] = useState<WeeklyAvailability | null>(null)
  const serviceNames = new Map((services.data?.results ?? []).map((s) => [s.id, s.name]))

  return (
    <section className="grid gap-4" aria-labelledby="availability-heading">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 id="availability-heading" className="text-lg font-semibold">
            Weekly availability
          </h2>
          <p className="text-muted-foreground text-sm">
            One calendar per person (e.g. each photographer): when they can take bookings, every week, in 15-minute
            blocks.
          </p>
        </div>
        <Button variant="outline" onClick={() => setForm({ open: true })}>
          <Plus /> Add availability
        </Button>
      </div>

      {isPending ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Skeleton className="h-36" />
          <Skeleton className="h-36" />
        </div>
      ) : isError ? (
        <div className="border-destructive/50 flex flex-col items-start gap-3 rounded-lg border p-4">
          <p className="text-destructive text-sm">Couldn't load weekly availabilities: {error.message}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : data.results.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-8 text-center">
          <CalendarDays className="text-muted-foreground size-8" />
          <p className="font-medium">No weekly availabilities yet</p>
          <p className="text-muted-foreground text-sm">Add one for each person who does your services.</p>
        </div>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {data.results.map((availability) => {
            const week = describeWeek(availability.availability)
            return (
              <li key={availability.id} className="bg-card grid content-start gap-2 rounded-xl border p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-semibold">{availability.name}</p>
                    <p className="text-muted-foreground text-xs tabular-nums">
                      {openHours(availability.availability)} hours a week available
                    </p>
                  </div>
                  <div className="flex shrink-0">
                    <Button variant="ghost" size="icon" aria-label={`Edit ${availability.name}`} onClick={() => setForm({ open: true, item: availability })}>
                      <Pencil />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Delete ${availability.name}`}
                      onClick={() => {
                        onError(null)
                        setDeleting(availability)
                      }}
                    >
                      <Trash2 className="text-destructive" />
                    </Button>
                  </div>
                </div>
                <ul className="text-xs tabular-nums">
                  {week.length === 0 ? (
                    <li className="text-destructive">No available hours: click edit to open some.</li>
                  ) : (
                    week.map((line) => <li key={line}>{line}</li>)
                  )}
                </ul>
                <div className="flex flex-wrap gap-1">
                  {availability.services.length === 0 ? (
                    <span className="text-muted-foreground text-xs">No services yet</span>
                  ) : (
                    availability.services.map((id) => (
                      <Badge key={id} variant="secondary">
                        {serviceNames.get(id) ?? `Service #${id}`}
                      </Badge>
                    ))
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      )}

      <AvailabilityEditorDialog
        open={form.open}
        onOpenChange={(open) => !open && setForm({ open: false })}
        availability={form.open ? form.item : undefined}
      />
      <DeleteAvailabilityDialog item={deleting} onOpenChange={(open) => !open && setDeleting(null)} onError={onError} />
    </section>
  )
}
