import {
  appendFiles,
  offreNotificationPath,
  pendingComplementCount,
  replaceFileAt,
  replyBlockReason,
  withoutFileAt,
} from "./complementsOffre";

describe("notes externes / compléments", () => {
  const awaiting = {
    id: "d1",
    can_reply: true,
    reply_expected: true,
    complement: { type: "reponse", status: "en_attente" },
  };
  const legacyDocument = {
    id: "legacy",
    can_reply: true,
    reply_expected: true,
    complement: { type: "document", status: "en_attente" },
  };

  test("une note informative n'ouvre pas de réponse", () => {
    expect(replyBlockReason({ id: "n1", can_reply: false, reply_expected: false }, "texte", [])).toBe(
      "Réponse non autorisée",
    );
  });

  test("texte seul, documents seuls ou les deux sont acceptés", () => {
    expect(replyBlockReason(awaiting, "", [])).toBe("Saisissez une réponse ou joignez un document");
    expect(replyBlockReason(awaiting, "Voici ma réponse", [])).toBe("");
    expect(replyBlockReason(awaiting, "", [{ name: "rempli.pdf" }])).toBe("");
    expect(replyBlockReason(awaiting, "Ci-joint", [{ name: "rempli.pdf" }])).toBe("");
    expect(replyBlockReason(legacyDocument, "Sans fichier", [])).toBe("");
  });

  test("les fichiers sélectionnés peuvent être retirés ou remplacés avant l'envoi", () => {
    const first = [{ name: "a.pdf" }, { name: "b.pdf" }];
    expect(withoutFileAt(first, 0).map((file) => file.name)).toEqual(["b.pdf"]);
    const replaced = replaceFileAt(first, 1, { name: "c.pdf" });
    expect(replaced.map((file) => file.name)).toEqual(["a.pdf", "c.pdf"]);
    expect(appendFiles(first, [{ name: "d.pdf" }])).toHaveLength(3);
  });

  test("le lien de notification ouvre la note concernée", () => {
    expect(offreNotificationPath({ demande_id: "off-1", complement_id: "c1" })).toBe(
      "/demandes-offres/off-1?complement=c1",
    );
    expect(offreNotificationPath({ demande_id: "off-1" }, { fromGestion: true })).toBe(
      "/demandes-offres/off-1?from=gestion",
    );
  });

  test("le compteur d'attente vient de la demande", () => {
    const demande = { nb_complements_en_attente: 1, notes_externes: [awaiting, legacyDocument] };
    expect(pendingComplementCount(demande)).toBe(1);
    expect(pendingComplementCount({ ...demande, nb_complements_en_attente: 0 })).toBe(0);
  });
});
