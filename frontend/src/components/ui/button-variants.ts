import { cva } from 'class-variance-authority';

/** The button's look, in one place, so a control that is not a `<button>` can wear it through
 * the same source: a link is an `<a href>`, and `cn(buttonVariants({ variant }), ...)` gives it
 * the variant without a second copy of these class strings. It sits in its own file because a
 * value exported beside a component breaks Fast Refresh (`react-refresh/only-export-components`). */
export const buttonVariants = cva(
    'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50',
    {
        variants: {
            variant: {
                default: 'bg-primary text-primary-foreground hover:bg-primary/90',
                secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
                destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
                outline:
                    'border border-input bg-transparent hover:bg-accent hover:text-accent-foreground',
                ghost: 'hover:bg-accent hover:text-accent-foreground',
            },
            size: {
                default: 'h-9 px-4 py-2',
                sm: 'h-8 px-3 text-xs',
                lg: 'h-10 px-6',
            },
        },
        defaultVariants: { variant: 'default', size: 'default' },
    },
);
