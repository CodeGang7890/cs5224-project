import { APP_NAME } from '@/config/app'
import { ProductManager } from '@/features/products'

export function ProductPage() {
  return (
    <section className="flex flex-col gap-6">
      <title>{`Product | ${APP_NAME}`}</title>
      <div className="grid gap-1">
        <h1 className="text-2xl font-bold tracking-tight">Products</h1>
        <p className="text-muted-foreground text-sm">Manage your business's products.</p>
      </div>
      <ProductManager />
    </section>
  )
}
