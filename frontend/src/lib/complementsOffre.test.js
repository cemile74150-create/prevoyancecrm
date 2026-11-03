import {
  appendFiles,
  offreNotificationPath,
  pendingComplementCount,
  replaceFileAt,
  replyBlockReason,
  withoutFileAt,
} from "./complementsOffre";

describe("demandes de complément", () => {
  const documentNote = {
    id: "d1",
    can_reply: true,
    reply_expected: true,
    complement: { type: "document", status: "en_attente" },
  };
  const infoNote = {
    id: "i1",
    can_reply: true,
    reply_expected: true,
    complement: { type: "information", status: "en_attente" },
  };

  test("une note informative n'ouvre pas de réponse", () => {
    expect(replyBlockReason({ id: "n1", can_reply: false, reply_expected: false }, "texte", [])).toBe(
      "Réponse non autorisée",
    );
  });

  test("un document est obligatoire seulement pour une demande de document", () => {
    expect(replyBlockReason(documentNote, "", [])).toBe("Ajoutez au moins un document");
    expect(replyBlockReason(documentNote, "", [{ name: "mandat.pdf" }])).toBe("");
    expect(replyBlockReason(infoNote, "12.03.1980", [])).toBe("");
    expect(replyBlockReason(infoNote, "", [])).toBe("Saisissez une réponse ou joignez un document");
  });

  test("les fichiers sélectionnés peuvent être retirés ou remplacés avant l'envoi", () => {
    const first = [{ name: "a.pdf" }, { name: "b.pdf" }];
    expect(withoutFileAt(first, 0).map((file) => file.name)).toEqual(["b.pdf"]);
    const replaced = replaceFileAt(first, 1, { name: "c.pdf" });
    expect(replaced.map((file) => file.name)).toEqual(["a.pdf", "c.pdf"]);
    expect(appendFiles(first, [{ name: "d.pdf" }])).toHaveLength(3);
  });

  test("le lien de notification ouvre la demande de complément", () => {
    expect(offreNotificationPath({ demande_id: "off-1", complement_id: "c1" })).toBe(
      "/demandes-offres/off-1?complement=c1",
    );
    expect(offreNotificationPath({ demande_id: "off-1" }, { fromGestion: true })).toBe(
      "/demandes-offres/off-1?from=gestion",
    );
  });

  test("le compteur d'attente vient de la demande et reste indépendant après relecture", () => {
    const demande = { nb_complements_en_attente: 1, notes_externes: [documentNote, infoNote] };
    expect(pendingComplementCount(demande)).toBe(1);
    expect(pendingComplementCount({ ...demande, nb_complements_en_attente: 0 })).toBe(0);
  });
});
