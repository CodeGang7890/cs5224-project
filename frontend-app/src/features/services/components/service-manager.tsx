import { useEffect, useRef, useState } from 'react'
import { CalendarDays, Pencil, Plus, Trash2, UserRound } from 'lucide-react'
import { useSearchParams } from 'react-router'

import { PaginationControls } from '@/components/common/pagination-controls'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { usePageParam } from '@/hooks/use-page-param'

import { SERVICES_PAGE_SIZE, useProviders, useServices } from '../hooks/use-services'
import type { Service, ServiceProvider } from '../types'
import { formatMinutes } from '../validation'
import { DeleteProviderDialog, DeleteServiceDialog } from './delete-dialogs'
import { ProviderFormDialog } from './provider-form-dialog'
import { ProviderSchedule } from './provider-schedule'
import { ServiceFormDialog } from './service-form-dialog'

const priceFormat = new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

type FormState<T> = { open: false } | { open: true; item?: T }

/** The Service tab: services (what customers book), service providers (who with) and their schedules (when). */
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
      <ProvidersSection onError={setActionError} />
    </div>
  )
}

function ServicesSection({ onError }: { onError: (message: string | null) => void }) {
  const [page, setPage] = usePageParam()
  const { data, isPending, isError, error, refetch, isPlaceholderData } = useServices(page)
  const providers = useProviders()
  const [form, setForm] = useState<FormState<Service>>({ open: false })
  const [deleting, setDeleting] = useState<Service | null>(null)
  const names = new Map((providers.data?.results ?? []).map((p) => [p.id, p.name]))

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
            Add a service (e.g. a photoshoot), and link it to the service providers who do it.
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
                      {service.service_providers.length === 0 ? (
                        <span className="text-destructive text-xs">No one: can't be booked</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {service.service_providers.map((id) => (
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

function ProvidersSection({ onError }: { onError: (message: string | null) => void }) {
  const { data, isPending, isError, error, refetch } = useProviders()
  const services = useServices(1)
  const [, setSearchParams] = useSearchParams()
  const [form, setForm] = useState<FormState<ServiceProvider>>({ open: false })
  const [deleting, setDeleting] = useState<ServiceProvider | null>(null)
  const scheduleRef = useRef<HTMLElement>(null)
  const serviceNames = new Map((services.data?.results ?? []).map((s) => [s.id, s.name]))

  const showSchedule = (provider: ServiceProvider) => {
    setSearchParams(
      (params) => {
        params.set('provider', String(provider.id))
        return params
      },
      { replace: true },
    )
    scheduleRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <>
      <section className="grid gap-4" aria-labelledby="providers-heading">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 id="providers-heading" className="text-lg font-semibold">
              Service providers
            </h2>
            <p className="text-muted-foreground text-sm">
              Who services are booked with: each photographer, teacher, room… with their own schedule.
            </p>
          </div>
          <Button variant="outline" onClick={() => setForm({ open: true })}>
            <Plus /> Add provider
          </Button>
        </div>

        {isPending ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
          </div>
        ) : isError ? (
          <div className="border-destructive/50 flex flex-col items-start gap-3 rounded-lg border p-4">
            <p className="text-destructive text-sm">Couldn't load service providers: {error.message}</p>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              Try again
            </Button>
          </div>
        ) : data.results.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-8 text-center">
            <UserRound className="text-muted-foreground size-8" />
            <p className="font-medium">No service providers yet</p>
            <p className="text-muted-foreground text-sm">Add one for each person (or room) your services are booked with.</p>
          </div>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.results.map((provider) => (
              <li key={provider.id} className="bg-card grid content-start gap-2 rounded-xl border p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 font-semibold">
                      {provider.name}
                      {!provider.is_active && <Badge variant="outline">Inactive</Badge>}
                    </p>
                    {provider.description && <p className="text-muted-foreground line-clamp-2 text-xs">{provider.description}</p>}
                  </div>
                  <div className="flex shrink-0">
                    <Button variant="ghost" size="icon" aria-label={`Edit ${provider.name}`} onClick={() => setForm({ open: true, item: provider })}>
                      <Pencil />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Delete ${provider.name}`}
                      onClick={() => {
                        onError(null)
                        setDeleting(provider)
                      }}
                    >
                      <Trash2 className="text-destructive" />
                    </Button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1">
                  {provider.services.length === 0 ? (
                    <span className="text-muted-foreground text-xs">No services yet: link them in a service's form.</span>
                  ) : (
                    provider.services.map((id) => (
                      <Badge key={id} variant="secondary">
                        {serviceNames.get(id) ?? `Service #${id}`}
                      </Badge>
                    ))
                  )}
                </div>
                <Button variant="outline" size="sm" className="justify-self-start" onClick={() => showSchedule(provider)}>
                  <CalendarDays /> View schedule
                </Button>
              </li>
            ))}
          </ul>
        )}

        <ProviderFormDialog
          open={form.open}
          onOpenChange={(open) => !open && setForm({ open: false })}
          provider={form.open ? form.item : undefined}
          onCreated={showSchedule}
        />
        <DeleteProviderDialog item={deleting} onOpenChange={(open) => !open && setDeleting(null)} onError={onError} />
      </section>

      {data && data.results.length > 0 && (
        <section ref={scheduleRef} className="grid scroll-mt-20 gap-4" aria-labelledby="schedule-heading">
          <div>
            <h2 id="schedule-heading" className="text-lg font-semibold">
              Schedules
            </h2>
            <p className="text-muted-foreground text-sm">
              Each provider's week in 15-minute blocks. Customers can book the available times; bookings put their
              time on hold until paid, then mark it booked.
            </p>
          </div>
          <ProviderSchedule providers={data.results} />
        </section>
      )}
    </>
  )
}
