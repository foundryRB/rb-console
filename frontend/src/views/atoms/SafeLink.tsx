export const SafeLink: React.FC<{ href: string; children: React.ReactNode }> = ({
    href,
    children,
}) => {
    const external = /^(https?:|mailto:)/i.test(href);
    return (
        <a
            href={href}
            {...(external ? { target: '_blank', rel: 'noreferrer noopener' } : {})}
            className="text-link underline underline-offset-2 hover:text-link/80"
        >
            {children}
        </a>
    );
};
