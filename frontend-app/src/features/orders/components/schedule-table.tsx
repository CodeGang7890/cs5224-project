import { Eye } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { shortPaymentReference } from "../payment-reference";
import type { ScheduleItem } from "../types";
import { DocumentLinks } from "./document-links";
import { OrderStatusBadge, SandboxBadge } from "./order-status-badge";
import { bookingCustomer, formatBookingTime } from "./schedule-format";

interface ScheduleTableProps {
  bookings: ScheduleItem[];
  onOpen: (id: number) => void;
}

/** Read-only list of bookings. Clicking a row (or View) opens the booking. */
export function ScheduleTable({ bookings, onOpen }: ScheduleTableProps) {
  return (
    <div className="rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="pl-4">Booking</TableHead>
            <TableHead>Customer</TableHead>
            <TableHead>Service</TableHead>
            <TableHead>When</TableHead>
            <TableHead>With</TableHead>
            <TableHead className="text-right">Total</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Invoice / receipt</TableHead>
            <TableHead className="w-12">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {bookings.map((booking) => (
            <TableRow
              key={booking.id}
              className="cursor-pointer"
              onClick={() => onOpen(booking.id)}
            >
              <TableCell className="pl-4">
                <div className="flex items-center gap-2">
                  <span className="font-medium tabular-nums">
                    #{booking.id}
                  </span>
                  {booking.is_sandbox && <SandboxBadge />}
                </div>
                <p
                  className="text-muted-foreground font-mono text-xs"
                  title={`Payment reference ${booking.payment_reference}`}
                >
                  {shortPaymentReference(booking.payment_reference)}
                </p>
              </TableCell>
              <TableCell>
                {bookingCustomer(booking) ?? (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell className="font-medium">
                {booking.schedule_data.service.name}
              </TableCell>
              <TableCell className="whitespace-nowrap tabular-nums">
                {formatBookingTime(booking)}
              </TableCell>
              <TableCell>
                {booking.service_provider_name ?? (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell className="text-right font-medium tabular-nums">
                ${booking.total}
              </TableCell>
              <TableCell>
                <OrderStatusBadge status={booking.order_status} />
              </TableCell>
              <TableCell>
                <DocumentLinks owner="booking" item={booking} compact />
              </TableCell>
              <TableCell>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`View booking #${booking.id}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    onOpen(booking.id);
                  }}
                >
                  <Eye />
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
