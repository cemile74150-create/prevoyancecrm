// @ts-nocheck
"use client";

import { useState } from "react";
import { Button } from "@/analyse-prevoyance/ui/button";

const MESSAGE =
  "Êtes-vous sûr de vouloir supprimer cet élément ? Cette action ne pourra pas être annulée.";

export function ConfirmDeleteButton({
  onConfirm,
  children,
  ariaLabel = "Supprimer",
  className,
  variant = "ghost",
  size = "sm",
}: {
  onConfirm: () => void;
  children?: React.ReactNode;
  ariaLabel?: string;
  className?: string;
  variant?: "ghost" | "outline" | "default";
  size?: "sm" | "icon";
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        type="button"
        variant={variant}
        size={size}
        className={className}
        aria-label={ariaLabel}
        onClick={() => setOpen(true)}
      >
        {children}
      </Button>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="presentation"
          onClick={() => setOpen(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-delete-title"
            className="w-full max-w-md rounded-lg border bg-background p-5 shadow-lg"
            onClick={(event) => event.stopPropagation()}
          >
            <p id="confirm-delete-title" className="text-sm">
              {MESSAGE}
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Annuler
              </Button>
              <Button
                type="button"
                onClick={() => {
                  setOpen(false);
                  onConfirm();
                }}
              >
                Supprimer
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
