"use strict";

// The server owns identity, permissions, selection, drafts and receipts.
// This page displays returned facts and sends proposals; only the bound button
// sends explicit confirmation. Text from users and records is always textContent.
const COPY = {
  es: {
    brandCaption: "Tu actividad, en claro.", demoAccount: "CUENTA",
    yourTransactions: "Tus movimientos", transactionsHint: "Movimientos disponibles para esta cuenta.",
    language: "Idioma", demoDisclosure: "DEMO: este entorno no mueve dinero ni envía solicitudes a un banco.",
    workspaceLabel: "ASISTENTE DE TRANSACCIONES", workspaceTitle: "Hablemos de tu movimiento.",
    demoBadge: "DEMO", reset: "Nueva sesión", conversationTitle: "Tu asistente",
    conversationSubtitle: "Consulta, revisa y decide con información.", local: "Local",
    loading: "Preparando tu sesión…", chooseTransaction: "Elige el movimiento que quieres revisar",
    intakeChoice: "Decidir si preparar una solicitud de revisión", prepareIntake: "Sí, preparar solicitud", declineIntake: "No, seguir consultando",
    draftLock: "Revisa la propuesta del panel y confirma o cancela para continuar.", messageLabel: "Escribe tu consulta",
    messagePlaceholder: "Pregunta por una transacción…", sendLabel: "Enviar mensaje",
    composerCaption: "Las acciones necesitan tu confirmación explícita.", detailsTitle: "En revisión",
    emptyTitle: "Comienza con un movimiento", emptyDetails: "Haz una consulta o elige uno de tus movimientos para ver sus detalles aquí.",
    reviewBeforeConfirm: "REVISA ANTES DE CONFIRMAR", confirm: "Confirmar y guardar", cancel: "Cancelar",
    draftFooter: "Todavía no se ha creado ningún caso con esta propuesta.", receiptsTitle: "Solicitudes guardadas",
    handoffTitle: "Para la revisión humana", handoffCaption: "Resumen preparado para revisión humana.",
    offerHandoff: "Preparar revisión humana", footer: "Factored AI & Data Hackathon 2026",
    footerProof: "Hechos trazables. Acciones confirmadas.", viewTransaction: "Ver movimiento ↗",
    customerFallback: "Cliente A", assistant: "CLARO", user: "TÚ",
    activeSession: "Sesión activa", expiredSession: "Sesión vencida", remaining: "min restantes",
    sessionExpired: "Tu sesión venció. Inicia una nueva sesión para continuar.",
    selected: "Movimiento seleccionado", amount: "Importe", merchant: "Comercio", unknownMerchant: "Comercio no informado",
    transactionDate: "Fecha del movimiento", processDate: "Fecha de proceso", transactionType: "Tipo",
    reference: "Referencia", status: "Estado registrado", timezoneUnknown: "Zona horaria no informada",
    snapshotNote: "Datos de una instantánea histórica. El estado corresponde al registro disponible.",
    sourceDetails: "Ver evidencia del registro", sourceRow: "Registro", sourceProof: "Huella de la evidencia",
    intakeTitle: "Abrir un caso de revisión", handoffDraftTitle: "Preparar revisión humana",
    intakeDescription: "Guardar una solicitud sobre este movimiento. No implica aprobar un reembolso.",
    handoffDescription: "Guardar un resumen para revisión humana.",
    expiresAt: "Propuesta válida hasta", draftExpired: "Esta propuesta venció. Cancélala y prepara una nueva.",
    outcomeUnverifiedTitle: "Resultado pendiente de verificar",
    outcomeUnverifiedDescription: "No pudimos comprobar si esta solicitud quedó guardada. Revisa la misma solicitud y vuelve a verificarla.",
    outcomeUnverifiedStep: "RESULTADO SIN VERIFICAR",
    outcomeUnverifiedFooter: "El resultado sigue sin verificar. La comprobación utiliza la misma solicitud; no prepares una nueva mientras resolvemos este resultado.",
    verifyAgain: "Verificar solicitud de nuevo", tryCancel: "Intentar cancelar",
    unverifiedExpired: "La propuesta venció. Puedes intentar comprobar el resultado de esta misma solicitud mientras tu sesión siga activa.",
    uncertainTransport: "No recibimos un resultado verificable de la confirmación. La solicitud podría haberse guardado. Revisa la misma propuesta y utiliza «Verificar solicitud de nuevo» para comprobarlo.",
    request: "Solicitud", escalationReason: "Motivo de revisión", attemptedSteps: "Lo que ya se hizo",
    unresolvedQuestions: "Lo que falta resolver", transactionFacts: "Movimiento relacionado", verifiedActions: "Casos ya registrados",
    noPendingQuestions: "No se especificaron preguntas pendientes.", noSelectedTransaction: "Sin movimiento seleccionado.",
    intakeReceipt: "Caso de revisión · guardado y verificado", handoffReceipt: "Revisión humana · guardada y verificada",
    actionVerified: "Solicitud guardada y verificada", receiptNote: "Usa esta referencia al consultar la solicitud.",
    transportError: "No pudimos conectar con la aplicación. Revisa que el servidor local esté activo y vuelve a intentar.",
    requestError: "No pudimos completar la solicitud. Vuelve a intentar o inicia una nueva sesión.",
    unexpectedResponse: "La aplicación devolvió una respuesta incompleta. Vuelve a intentar.",
    prompts: [
      ["Buscar una compra", "Quiero consultar una compra"],
      ["No reconozco un cargo", "No reconozco esta compra"],
      ["Hablar con una persona", "Quiero hablar con una persona"]
    ],
    statuses: {Approved: "Aprobado", Declined: "Rechazado", Pending: "Pendiente", Reversed: "Revertido"},
    types: {Deposit: "Depósito", Withdrawal: "Retiro", Transfer: "Transferencia", Purchase: "Compra", Payment: "Pago", Adjustment: "Ajuste"},
    reasons: {human_requested: "La persona solicita atención humana", unsupported_request: "La solicitud necesita atención fuera de este asistente", ineligible_intake: "El movimiento requiere revisión fuera del ticket de compras", existing_case_unverified: "Se solicita seguimiento a un caso anterior que este asistente no puede verificar", tool_failure: "No se pudo completar una operación", missing_information: "Se necesita información adicional", unresolved: "La consulta requiere revisión adicional"},
    steps: {search_attempted: "Se buscaron movimientos", search_needs_filters: "Se solicitaron detalles para buscar", search_no_match: "La búsqueda no encontró coincidencias", search_ambiguous: "Se encontraron varias coincidencias", transaction_answered: "Se explicaron los datos del movimiento", choice_rejected: "Se rechazó una selección que no estaba disponible", intake_prepared: "Se preparó una solicitud de revisión", handoff_prepared: "Se preparó un resumen para revisión humana", action_verified: "Se guardó y verificó una solicitud", action_cancelled: "Se canceló una propuesta", confirmation_failed: "No se pudo verificar la confirmación"}
  },
  pt: {
    brandCaption: "Sua atividade, com clareza.", demoAccount: "CONTA",
    yourTransactions: "Suas transações", transactionsHint: "Transações disponíveis para esta conta.",
    language: "Idioma", demoDisclosure: "DEMO: este ambiente não movimenta dinheiro nem envia solicitações a um banco.",
    workspaceLabel: "ASSISTENTE DE TRANSAÇÕES", workspaceTitle: "Vamos falar da sua transação.",
    demoBadge: "DEMO", reset: "Nova sessão", conversationTitle: "Seu assistente",
    conversationSubtitle: "Consulte, revise e decida com informação.", local: "Local",
    loading: "Preparando sua sessão…", chooseTransaction: "Escolha a transação que deseja revisar",
    intakeChoice: "Decidir se deseja preparar uma solicitação de revisão", prepareIntake: "Sim, preparar solicitação", declineIntake: "Não, continuar consultando",
    draftLock: "Revise a proposta no painel e confirme ou cancele para continuar.", messageLabel: "Escreva sua consulta",
    messagePlaceholder: "Pergunte sobre uma transação…", sendLabel: "Enviar mensagem",
    composerCaption: "As ações precisam da sua confirmação explícita.", detailsTitle: "Em revisão",
    emptyTitle: "Comece com uma transação", emptyDetails: "Faça uma consulta ou escolha uma de suas transações para ver os detalhes aqui.",
    reviewBeforeConfirm: "REVISE ANTES DE CONFIRMAR", confirm: "Confirmar e salvar", cancel: "Cancelar",
    draftFooter: "Nenhum caso foi criado com esta proposta ainda.", receiptsTitle: "Solicitações salvas",
    handoffTitle: "Para a revisão humana", handoffCaption: "Resumo preparado para revisão humana.",
    offerHandoff: "Preparar revisão humana", footer: "Factored AI & Data Hackathon 2026",
    footerProof: "Fatos rastreáveis. Ações confirmadas.", viewTransaction: "Ver transação ↗",
    customerFallback: "Cliente A", assistant: "CLARO", user: "VOCÊ",
    activeSession: "Sessão ativa", expiredSession: "Sessão expirada", remaining: "min restantes",
    sessionExpired: "Sua sessão expirou. Inicie uma nova sessão para continuar.",
    selected: "Transação selecionada", amount: "Valor", merchant: "Estabelecimento", unknownMerchant: "Estabelecimento não informado",
    transactionDate: "Data da transação", processDate: "Data de processamento", transactionType: "Tipo",
    reference: "Referência", status: "Estado registrado", timezoneUnknown: "Fuso horário não informado",
    snapshotNote: "Dados de um registro histórico. O estado corresponde ao registro disponível.",
    sourceDetails: "Ver evidência do registro", sourceRow: "Registro", sourceProof: "Identificador da evidência",
    intakeTitle: "Abrir um caso de revisão", handoffDraftTitle: "Preparar revisão humana",
    intakeDescription: "Salvar uma solicitação sobre esta transação. Isso não significa aprovar um reembolso.",
    handoffDescription: "Salvar um resumo para revisão humana.",
    expiresAt: "Proposta válida até", draftExpired: "Esta proposta expirou. Cancele e prepare uma nova.",
    outcomeUnverifiedTitle: "Resultado aguardando verificação",
    outcomeUnverifiedDescription: "Não conseguimos verificar se esta solicitação foi salva. Revise a mesma solicitação e tente verificar novamente.",
    outcomeUnverifiedStep: "RESULTADO NÃO VERIFICADO",
    outcomeUnverifiedFooter: "O resultado ainda não foi verificado. A verificação usa a mesma solicitação; não prepare uma nova enquanto este resultado estiver pendente.",
    verifyAgain: "Verificar solicitação novamente", tryCancel: "Tentar cancelar",
    unverifiedExpired: "A proposta expirou. Você pode tentar verificar o resultado desta mesma solicitação enquanto sua sessão estiver ativa.",
    uncertainTransport: "Não recebemos um resultado verificável da confirmação. A solicitação pode ter sido salva. Revise a mesma proposta e use «Verificar solicitação novamente» para conferir.",
    request: "Solicitação", escalationReason: "Motivo da revisão", attemptedSteps: "O que já foi feito",
    unresolvedQuestions: "O que falta resolver", transactionFacts: "Transação relacionada", verifiedActions: "Casos já registrados",
    noPendingQuestions: "Nenhuma pergunta pendente foi informada.", noSelectedTransaction: "Nenhuma transação selecionada.",
    intakeReceipt: "Caso de revisão · salvo e verificado", handoffReceipt: "Revisão humana · salva e verificada",
    actionVerified: "Solicitação salva e verificada", receiptNote: "Use esta referência ao consultar a solicitação.",
    transportError: "Não conseguimos conectar ao aplicativo. Verifique se o servidor local está ativo e tente novamente.",
    requestError: "Não conseguimos concluir a solicitação. Tente novamente ou inicie uma nova sessão.",
    unexpectedResponse: "O aplicativo retornou uma resposta incompleta. Tente novamente.",
    prompts: [
      ["Buscar uma compra", "Quero consultar uma compra"],
      ["Não reconheço uma cobrança", "Não reconheço esta compra"],
      ["Falar com uma pessoa", "Quero falar com uma pessoa"]
    ],
    statuses: {Approved: "Aprovado", Declined: "Recusado", Pending: "Pendente", Reversed: "Estornado"},
    types: {Deposit: "Depósito", Withdrawal: "Saque", Transfer: "Transferência", Purchase: "Compra", Payment: "Pagamento", Adjustment: "Ajuste"},
    reasons: {human_requested: "A pessoa solicita atendimento humano", unsupported_request: "A solicitação precisa de atendimento fora deste assistente", ineligible_intake: "A transação precisa de revisão fora do ticket de compras", existing_case_unverified: "Foi solicitado acompanhamento de um caso anterior que este assistente não consegue verificar", tool_failure: "Não foi possível concluir uma operação", missing_information: "São necessárias informações adicionais", unresolved: "A consulta precisa de revisão adicional"},
    steps: {search_attempted: "Foram pesquisadas transações", search_needs_filters: "Foram solicitados detalhes para pesquisar", search_no_match: "A pesquisa não encontrou correspondências", search_ambiguous: "Foram encontradas várias correspondências", transaction_answered: "Os dados da transação foram explicados", choice_rejected: "Foi rejeitada uma seleção que não estava disponível", intake_prepared: "Foi preparada uma solicitação de revisão", handoff_prepared: "Foi preparado um resumo para revisão humana", action_verified: "Uma solicitação foi salva e verificada", action_cancelled: "Uma proposta foi cancelada", confirmation_failed: "Não foi possível verificar a confirmação"}
  }
};

const PRIVATE_COPY = {
  es: {
    snapshotNote: "Registro histórico. El estado corresponde a la versión disponible del registro."
  },
  pt: {
    snapshotNote: "Registro histórico. O estado corresponde à versão disponível do registro."
  }
};

let serverState = null;
let busy = false;
let activeNotice = "";
const $ = (id) => document.getElementById(id);
const strings = () => {
  const language = serverState?.language === "pt" ? "pt" : "es";
  const copy = serverState?.data_mode === "private_cohort"
    ? {...COPY[language], ...PRIVATE_COPY[language]} : COPY[language];
  return {...copy, local: serverState?.route_mode === "learned_preview"
    ? "IA local" : language === "pt" ? "Regras locais" : "Reglas locales"};
};
const tr = (key) => strings()[key];
const asText = (value) => typeof value === "string" ? value : "";

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text);
  return element;
}

function showNotice(text) {
  activeNotice = asText(text);
  $("notice").textContent = activeNotice;
  $("notice").hidden = !activeNotice;
}

function sessionIsActive() {
  if (!serverState?.session?.active) return false;
  const expiry = Date.parse(serverState.session.expires_at);
  return Number.isFinite(expiry) && expiry > Date.now();
}

function draftIsExpired() {
  if (!serverState?.pending_draft) return false;
  const expiry = Date.parse(serverState.pending_draft.expires_at);
  return !Number.isFinite(expiry) || expiry <= Date.now();
}

function draftExpiryText() {
  const draft = serverState?.pending_draft;
  if (!draft) return "";
  if (draftIsExpired()) return tr(draft.outcome_unverified ? "unverifiedExpired" : "draftExpired");
  return `${tr("expiresAt")} ${expiryText(draft.expires_at)}`;
}

function dateText(raw, short = false) {
  // Preserve the source's calendar fields; a naive historical timestamp must not
  // be interpreted as the browser's timezone or silently shifted to another day.
  const value = asText(raw);
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(value);
  if (!match) return value;
  const display = `${match[3]}/${match[2]}/${match[1]}`;
  return short || !match[4] ? display : `${display} · ${match[4]}:${match[5]}`;
}

function expiryText(raw) {
  const value = new Date(raw);
  if (Number.isNaN(value.getTime())) return "";
  return value.toLocaleTimeString(serverState?.language === "pt" ? "pt-BR" : "es-MX", {hour: "2-digit", minute: "2-digit"});
}

function amountText(record) {
  // Decimal strings remain exact and in their original currency.
  return `${asText(record?.amount)} ${asText(record?.currency)}`.trim();
}

function localizedStatus(value) {
  return strings().statuses[value] || tr("status");
}

function localizedType(value) {
  return strings().types[value] || tr("transactionType");
}

function applyLanguage() {
  const language = serverState?.language === "pt" ? "pt" : "es";
  document.documentElement.lang = language;
  document.title = language === "pt" ? "Claro · Assistente de transações" : "Claro · Asistente de transacciones";
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    const translation = tr(element.dataset.i18n);
    if (typeof translation === "string") element.textContent = translation;
  });
  $("language").value = language;
  $("message-input").placeholder = tr("messagePlaceholder");
  $("send").setAttribute("aria-label", tr("sendLabel"));
  $("language").setAttribute("aria-label", tr("language"));
  $("quick-prompts").setAttribute("aria-label", language === "pt" ? "Sugestões" : "Sugerencias");
  $("intake-offer").setAttribute("aria-label", tr("intakeChoice"));
  $("demo-badge").setAttribute("title", tr("demoDisclosure"));
  $("demo-badge").setAttribute("aria-label", tr("demoDisclosure"));
  document.querySelector(".sidebar").setAttribute("aria-label", tr("demoAccount"));
  document.querySelector(".review-panel").setAttribute("aria-label", tr("detailsTitle"));
}

function renderTransactions() {
  const container = $("transactions");
  container.replaceChildren();
  const records = Array.isArray(serverState.transactions) ? serverState.transactions : [];
  $("transaction-count").textContent = String(records.length);
  records.forEach((record) => {
    const card = node("article", "transaction-card");
    if (record.transaction_id === serverState.selected_transaction?.transaction_id) card.classList.add("selected");
    const top = node("div", "transaction-top");
    const icon = node("span", "merchant-icon", "▤");
    icon.setAttribute("aria-hidden", "true");
    const title = node("div");
    title.append(node("h3", "", record.merchant_name || tr("unknownMerchant")), node("p", "transaction-date", dateText(record.transaction_date, true)));
    top.append(icon, title);
    const bottom = node("div", "transaction-bottom");
    const amount = node("p", "transaction-amount", asText(record.amount));
    amount.append(node("small", "", asText(record.currency)));
    const button = node("button", "transaction-button", tr("viewTransaction"));
    button.type = "button";
    button.dataset.proposal = "true";
    button.addEventListener("click", () => action("inquire", {transaction_id: record.transaction_id}));
    bottom.append(amount, button);
    card.append(top, bottom);
    container.append(card);
  });
}

function renderMessages(scrollState) {
  const container = $("messages");
  container.replaceChildren();
  const messages = Array.isArray(serverState.messages) ? serverState.messages : [];
  messages.forEach((message) => {
    const role = message.role === "user" ? "user" : "assistant";
    const row = node("div", `message ${role}`);
    if (role === "assistant") {
      const marker = node("span", "message-bullet", "✦");
      marker.setAttribute("aria-hidden", "true");
      row.append(marker);
    }
    const content = node("div", "message-content");
    content.append(node("p", "message-label", tr(role)), node("p", "message-text", asText(message.text)));
    if (role === "assistant" && message.status === "action_verified") {
      content.append(node("p", "message-metadata", `✓ ${tr("actionVerified")}`));
    }
    row.append(content);
    container.append(row);
  });
  container.scrollTop = scrollState.nearBottom ? container.scrollHeight : scrollState.scrollTop;
}

function renderCandidates() {
  const candidates = Array.isArray(serverState.candidate_ids) ? serverState.candidate_ids : [];
  $("candidate-panel").hidden = candidates.length === 0;
  $("candidates").replaceChildren();
  candidates.forEach((transactionId) => {
    if (typeof transactionId !== "string") return;
    const record = (serverState.transactions || []).find((entry) => entry.transaction_id === transactionId);
    const button = node("button", "candidate-button");
    button.type = "button";
    button.dataset.proposal = "true";
    const label = node("span");
    label.append(node("span", "candidate-merchant", record?.merchant_name || tr("selected")), node("span", "candidate-ref", transactionId));
    button.append(label);
    if (record) button.append(node("span", "candidate-amount", amountText(record)));
    button.append(node("span", "candidate-arrow", "→"));
    button.addEventListener("click", () => action("choose", {transaction_id: transactionId}));
    $("candidates").append(button);
  });
}

function renderIntakeOffer() {
  const offer = serverState.intake_offer;
  // This is consent to prepare a proposal, never confirmation of an action.
  // Only a server-issued offer can expose these controls or bind their request.
  const validOffer = offer && typeof offer.offer_id === "string" && offer.offer_id.length > 0
    && typeof offer.transaction_id === "string" && offer.transaction_id.length > 0;
  $("intake-offer").hidden = !validOffer || Boolean(serverState.pending_draft);
}

function factRow(label, value) {
  const row = node("div", "fact-row");
  row.append(node("dt", "", label), node("dd", "", value));
  return row;
}

function renderSelected() {
  const target = $("selected-transaction");
  target.replaceChildren();
  const record = serverState.selected_transaction;
  if (!record) {
    const empty = node("div", "empty-detail");
    empty.append(node("h3", "", tr("emptyTitle")), node("p", "", tr("emptyDetails")));
    target.append(empty);
    return;
  }
  const merchant = node("div", "selected-merchant");
  const icon = node("span", "merchant-icon", "▤");
  icon.setAttribute("aria-hidden", "true");
  const heading = node("div");
  heading.append(node("h3", "", record.merchant_name || tr("unknownMerchant")), node("p", "", tr("selected")));
  merchant.append(icon, heading);
  const amount = node("p", "selected-amount", asText(record.amount));
  amount.append(node("span", "", asText(record.currency)));
  const facts = node("dl", "facts-list");
  facts.append(factRow(tr("transactionDate"), dateText(record.transaction_date)), factRow(tr("processDate"), dateText(record.process_date)), factRow(tr("transactionType"), localizedType(record.transaction_type)), factRow(tr("reference"), asText(record.transaction_id)));
  const timestamp = asText(record.transaction_date);
  if (timestamp && !/(?:Z|[+-]\d{2}:\d{2})$/.test(timestamp)) facts.append(factRow(tr("timezoneUnknown"), "—"));
  target.append(merchant, amount, node("span", "record-status", localizedStatus(record.transaction_status)), facts, node("p", "record-caption", tr("snapshotNote")));
  if (Array.isArray(record.sources) && record.sources.length) {
    const details = node("details", "proof-details");
    details.append(node("summary", "", tr("sourceDetails")));
    const list = node("ul");
    record.sources.forEach((source) => {
      const item = node("li", "", `${asText(source.file)} · ${tr("sourceRow")} ${source.row_number}`);
      if (source.row_sha256) item.append(node("p", "", `${tr("sourceProof")}: ${asText(source.row_sha256)}`));
      list.append(item);
    });
    details.append(list);
    target.append(details);
  }
}

function renderDraft() {
  const draft = serverState.pending_draft;
  $("draft-card").hidden = !draft;
  if (!draft) return;
  const unverified = draft.outcome_unverified === true;
  $("draft-title").textContent = tr(unverified ? "outcomeUnverifiedTitle" : draft.kind === "handoff" ? "handoffDraftTitle" : "intakeTitle");
  $("draft-description").textContent = tr(unverified ? "outcomeUnverifiedDescription" : draft.kind === "handoff" ? "handoffDescription" : "intakeDescription");
  document.querySelector('.draft-step [data-i18n]').textContent = tr(unverified ? "outcomeUnverifiedStep" : "reviewBeforeConfirm");
  document.querySelector('.draft-footer').textContent = tr(unverified ? "outcomeUnverifiedFooter" : "draftFooter");
  $("confirm").textContent = tr(unverified ? "verifyAgain" : "confirm");
  $("cancel").textContent = tr(unverified ? "tryCancel" : "cancel");
  $("draft-summary").textContent = asText(draft.summary) || `${tr("request")}: ${asText(draft.request)}`;
  $("draft-packet").replaceChildren();
  if (draft.packet && typeof draft.packet === "object") renderPacket($("draft-packet"), draft.packet, draft.kind === "handoff");
  $("draft-expiry").textContent = draftExpiryText();
}

function renderReceipts() {
  const receipts = Array.isArray(serverState.receipts) ? serverState.receipts : [];
  $("receipts-card").hidden = receipts.length === 0;
  $("receipts").replaceChildren();
  receipts.forEach((receipt) => {
    const item = node("article", "receipt-item");
    item.append(node("span", "receipt-kind", tr(receipt.kind === "handoff" ? "handoffReceipt" : "intakeReceipt")), node("span", "receipt-reference", asText(receipt.case_id)), node("p", "receipt-text", asText(receipt.text)), node("p", "receipt-note", tr("receiptNote")));
    $("receipts").append(item);
  });
}

function handoffSection(label, value, list = false) {
  const section = node("section", "handoff-section");
  section.append(node("h3", "", label));
  if (list) {
    const entries = node("ul");
    value.forEach((entry) => entries.append(node("li", "", entry)));
    section.append(entries);
  } else section.append(node("p", "", value));
  return section;
}

function renderPacket(target, packet, includeHandoff = true) {
  target.append(handoffSection(tr("request"), asText(packet.request)));
  const reason = strings().reasons[packet.escalation_reason];
  if (includeHandoff && reason) target.append(handoffSection(tr("escalationReason"), reason));
  const facts = packet.facts;
  if (facts && typeof facts === "object") {
    const lines = [
      `${tr("reference")}: ${asText(facts.transaction_id)}`,
      `${tr("merchant")}: ${facts.merchant_name || tr("unknownMerchant")}`,
      `${tr("amount")}: ${amountText(facts)}`,
      `${tr("transactionDate")}: ${dateText(facts.transaction_date)}`,
      `${tr("processDate")}: ${dateText(facts.process_date)}`,
      `${tr("transactionType")}: ${localizedType(facts.transaction_type)}`,
      `${tr("status")}: ${localizedStatus(facts.transaction_status)}`
    ];
    if (facts.transaction_date && !/(?:Z|[+-]\d{2}:\d{2})$/.test(facts.transaction_date)) lines.push(tr("timezoneUnknown"));
    target.append(handoffSection(tr("transactionFacts"), lines, true));
  } else target.append(handoffSection(tr("transactionFacts"), tr("noSelectedTransaction")));
  if (includeHandoff) {
    const steps = Array.isArray(packet.attempted_steps) ? packet.attempted_steps.map((step) => strings().steps[step]).filter(Boolean) : [];
    if (steps.length) target.append(handoffSection(tr("attemptedSteps"), steps, true));
    const prior = Array.isArray(packet.verified_actions) ? packet.verified_actions : [];
    if (prior.length) {
      target.append(handoffSection(tr("verifiedActions"), prior.map((entry) => `${tr(entry.kind === "handoff" ? "handoffReceipt" : "intakeReceipt")}: ${asText(entry.case_id)}`), true));
    }
    const questions = Array.isArray(packet.unresolved_questions) ? packet.unresolved_questions.filter((entry) => typeof entry === "string") : [];
    if (questions.length || packet.escalation_reason !== "human_requested") {
      target.append(handoffSection(tr("unresolvedQuestions"), questions.length ? questions : tr("noPendingQuestions"), questions.length > 0));
    }
  }
  if (Array.isArray(packet.sources) && packet.sources.length) {
    const details = node("details", "proof-details");
    details.append(node("summary", "", tr("sourceDetails")));
    const entries = node("ul");
    packet.sources.forEach((source) => {
      const item = node("li", "", `${asText(source.file)} · ${tr("sourceRow")} ${source.row_number}`);
      if (source.row_sha256) item.append(node("p", "", `${tr("sourceProof")}: ${asText(source.row_sha256)}`));
      entries.append(item);
    });
    details.append(entries);
    target.append(details);
  }
}

function renderHandoff() {
  const packet = serverState.handoff;
  $("handoff-card").hidden = !packet;
  $("handoff").replaceChildren();
  if (!packet) return;
  renderPacket($("handoff"), packet);
}

function renderPrompts() {
  $("quick-prompts").replaceChildren();
  const selectedId = asText(serverState.selected_transaction?.transaction_id);
  strings().prompts.forEach(([label, text], index) => {
    if (index === 1 && !selectedId.trim()) return;
    const button = node("button", "prompt-button", label);
    button.type = "button";
    button.dataset.proposal = "true";
    if (index === 1) {
      // Bind this proposal to the selection that was rendered. The server must
      // reject a stale ID instead of applying it to a newer selected record.
      button.title = `${tr("selected")}: ${selectedId}`;
      button.addEventListener("click", () => action("dispute_selected", {transaction_id: selectedId}));
    } else button.addEventListener("click", () => action("message", {text}));
    $("quick-prompts").append(button);
  });
}

function refreshControls() {
  const active = sessionIsActive();
  const pending = Boolean(serverState?.pending_draft);
  const locked = busy || !active || pending;
  document.querySelectorAll('[data-proposal="true"]').forEach((button) => {button.disabled = locked;});
  $("message-input").disabled = locked;
  $("send").disabled = locked || !$("message-input").value.trim();
  $("language").disabled = busy || !active || pending;
  $("reset").disabled = busy;
  // Reconciliation may read an already-written case after the draft's TTL.
  // The server remains responsible for denying a new write after expiration.
  $("confirm").disabled = busy || !active || !pending || (draftIsExpired() && serverState?.pending_draft?.outcome_unverified !== true);
  // The server still checks expiry/consent. Cancelling is allowed as an explicit
  // attempt to discard an expired proposal; it cannot assert that a case exists.
  $("cancel").disabled = busy || !active || !pending;
  $("offer-handoff").disabled = locked;
  $("offer-handoff").hidden = !serverState?.offers_handoff || pending || !active;
  $("decline-handoff").disabled = locked;
  $("decline-handoff").hidden = !serverState?.handoff_offer || pending || !active;
  $("draft-lock-note").hidden = !pending;
  $("composer").setAttribute("aria-busy", String(busy));
  const expiry = Date.parse(serverState?.session?.expires_at);
  const remaining = Math.max(0, Math.ceil((expiry - Date.now()) / 60000));
  $("session-label").textContent = active ? `${tr("activeSession")} · ${remaining} ${tr("remaining")}` : tr("expiredSession");
  $("session-dot").classList.toggle("expired", !active);
  if (serverState?.pending_draft) $("draft-expiry").textContent = draftExpiryText();
}

function render() {
  if (!serverState) return;
  const messages = $("messages");
  // Capture the reading position before dynamic controls change chat height.
  const scrollState = {
    nearBottom: messages.scrollHeight - messages.scrollTop - messages.clientHeight < 90,
    scrollTop: messages.scrollTop
  };
  applyLanguage();
  $("customer-label").textContent = asText(serverState.session?.customer_label) || tr("customerFallback");
  renderTransactions();
  renderCandidates();
  renderIntakeOffer();
  renderSelected();
  renderDraft();
  renderReceipts();
  renderHandoff();
  renderPrompts();
  refreshControls();
  if (!sessionIsActive() && !activeNotice) showNotice(tr("sessionExpired"));
  // Measure the final synchronous layout before following the newest reply.
  renderMessages(scrollState);
}

async function readResponse(response) {
  let data;
  try {data = await response.json();} catch {throw new Error(tr("unexpectedResponse"));}
  if (data && typeof data === "object" && Array.isArray(data.messages) && typeof data.csrf_token === "string") {
    serverState = data;
    render();
  }
  if (data?.error?.outcome_unverified && serverState?.pending_draft) {
    serverState.pending_draft.outcome_unverified = true;
    renderDraft();
  }
  if (data?.error?.text) showNotice(asText(data.error.text));
  else if (!response.ok) showNotice(tr("requestError"));
  return data;
}

async function action(name, fields = {}) {
  if (busy || !serverState?.csrf_token) return;
  if (name !== "reset" && !sessionIsActive()) {showNotice(tr("sessionExpired")); return;}
  busy = true;
  showNotice("");
  refreshControls();
  try {
    const response = await fetch("/api/action", {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: {"Content-Type": "application/json", "Accept": "application/json"},
      body: JSON.stringify({action: name, csrf_token: serverState.csrf_token, ...fields})
    });
    await readResponse(response);
    if (response.ok && (name === "message" || name === "reset")) {$("message-input").value = ""; $("message-input").rows = 1;}
  } catch (error) {
    if (name === "confirm" && fields.confirmed === true && serverState?.pending_draft?.draft_id === fields.draft_id) {
      // A lost response cannot prove that the server did not commit. Retain this
      // exact proposal and let the owner explicitly reconcile its result.
      serverState.pending_draft.outcome_unverified = true;
      renderDraft();
      showNotice(tr("uncertainTransport"));
    } else showNotice(error instanceof TypeError ? tr("transportError") : error.message || tr("requestError"));
  }
  finally {busy = false; refreshControls();}
}

function focusComposerIfAvailable() {
  if (!busy && sessionIsActive() && !$("message-input").disabled && !serverState?.pending_draft) {
    $("message-input").focus({preventScroll: true});
  }
}

$("composer").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = $("message-input").value.trim();
  if (text && !$("message-input").disabled) {
    await action("message", {text});
    // Disabling the textarea during the request removes browser focus. Restore
    // it only after the server response leaves the composer available.
    focusComposerIfAvailable();
  }
});
$("message-input").addEventListener("input", () => {
  $("message-input").rows = Math.min(4, Math.max(1, $("message-input").value.split("\n").length));
  refreshControls();
});
$("message-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("composer").requestSubmit();
  }
});
$("language").addEventListener("change", () => action("language", {language: $("language").value}));
$("reset").addEventListener("click", () => action("reset"));
$("confirm").addEventListener("click", () => {
  const draftId = serverState?.pending_draft?.draft_id;
  if (draftId) action("confirm", {draft_id: draftId, confirmed: true});
});
$("cancel").addEventListener("click", () => {
  const draftId = serverState?.pending_draft?.draft_id;
  if (draftId) action("cancel", {draft_id: draftId});
});
$("offer-handoff").addEventListener("click", () => {
  const offerId = asText(serverState?.handoff_offer?.offer_id);
  if (offerId) return action("handoff_decision", {offer_id: offerId, prepare: true});
  const originalRequest = asText(serverState?.handoff_request);
  action("prepare_handoff", {request: originalRequest.trim() ? originalRequest : strings().prompts[2][1]});
});
$("decline-handoff").addEventListener("click", () => {
  const offerId = asText(serverState?.handoff_offer?.offer_id);
  if (offerId) action("handoff_decision", {offer_id: offerId, prepare: false});
});
$("accept-intake").addEventListener("click", () => {
  const offerId = asText(serverState?.intake_offer?.offer_id);
  if (offerId) action("intake_decision", {offer_id: offerId, prepare: true});
});
$("decline-intake").addEventListener("click", async () => {
  const offerId = asText(serverState?.intake_offer?.offer_id);
  if (offerId) {
    await action("intake_decision", {offer_id: offerId, prepare: false});
    focusComposerIfAvailable();
  }
});

async function initialize() {
  $("message-input").disabled = true;
  $("send").disabled = true;
  $("language").disabled = true;
  $("reset").disabled = true;
  try {
    const response = await fetch("/api/state", {credentials: "same-origin", cache: "no-store", headers: {"Accept": "application/json"}});
    await readResponse(response);
    if (!serverState) showNotice(tr("unexpectedResponse"));
  } catch {showNotice(tr("transportError"));}
  if (serverState) refreshControls();
}

setInterval(() => {if (serverState) refreshControls();}, 5000);
initialize();
