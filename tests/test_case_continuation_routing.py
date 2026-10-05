"""Synthetic support-continuation predicates; no workload or source reads."""

import unittest

from bank_service.routing import RoutingError, is_case_continuation


class CaseContinuationTests(unittest.TestCase):
    def test_spanish_existing_case_requests(self):
        for text in (
            "Quiero retomar el caso de atención al cliente.",
            "Necesito dar seguimiento a mi reclamo.",
            "¿Cuál es el estado de mi reclamación?",
            "Presenté un reclamo ayer. Quisiera saber cómo va.",
            "Quiero revisar el ticket que abrí la semana pasada.",
            "Ya envié una queja y quisiera conocer su avance.",
            "¿Puedes verificar la solicitud de revisión anterior?",
            "No quiero abrir otro caso; quiero retomar mi reclamo anterior.",
            "Quiero saber del caso que ya tengo.",
        ):
            with self.subTest(text=text):
                self.assertTrue(is_case_continuation(text, "es"))

    def test_portuguese_existing_case_requests(self):
        for text in (
            "Quero retomar o caso que deixei pendente.",
            "Preciso acompanhar minha reclamação.",
            "Qual é o andamento do meu chamado?",
            "Registrei uma reclamação ontem. Quero saber como está.",
            "Gostaria de conferir o protocolo que já abri.",
            "Quero dar continuidade ao pedido de revisão.",
            "Preciso de uma atualização sobre minha queixa.",
            "Não quero abrir outra reclamação; quero acompanhar meu chamado anterior.",
        ):
            with self.subTest(text=text):
                self.assertTrue(is_case_continuation(text, "pt"))

    def test_new_disputes_do_not_imply_an_existing_support_case(self):
        for text, language in (
            ("Quiero abrir un reclamo por esta compra.", "es"),
            ("Necesito crear un caso y consultar su estado.", "es"),
            ("No reconozco esta compra y quiero presentar una queja.", "es"),
            ("Quero abrir uma reclamação e acompanhar o andamento.", "pt"),
            ("Preciso criar um chamado para esta cobrança.", "pt"),
            ("Quero registrar uma reclamação sobre meu pagamento.", "pt"),
        ):
            with self.subTest(text=text):
                self.assertFalse(is_case_continuation(text, language))

    def test_transaction_and_other_requests_remain_outside_this_guard(self):
        for text, language in (
            ("Quiero consultar la compra que hice ayer.", "es"),
            ("Mi suscripción estaba cancelada y aun así me cobraron.", "es"),
            ("Quiero saber el estado de mi solicitud de crédito.", "es"),
            ("¿Qué es una reclamación?", "es"),
            ("Hay un caso pendiente.", "es"),
            ("No quiero retomar mi caso anterior; quiero consultar la compra.", "es"),
            ("Todavía no tengo un caso abierto, quiero consultar este cargo.", "es"),
            ("Quiero revisar el reclamo que no presenté.", "es"),
            ("Quero consultar o pagamento anterior.", "pt"),
            ("Minha assinatura foi cancelada, mas fui cobrado.", "pt"),
            ("Qual é o estado do meu pedido de empréstimo?", "pt"),
            ("O que significa reclamação?", "pt"),
            ("Existe uma reclamação pendente.", "pt"),
            ("Não quero acompanhar minha reclamação; quero consultar a compra.", "pt"),
            ("Não tenho um caso aberto, quero verificar a compra.", "pt"),
            ("Quero verificar a reclamação que não registrei.", "pt"),
            ("Hola", "es"),
            ("sim", "pt"),
        ):
            with self.subTest(text=text):
                self.assertFalse(is_case_continuation(text, language))

    def test_normalizes_case_accents_and_compatibility_characters(self):
        self.assertTrue(is_case_continuation("¿ＣＵÁＬ es el ESTADO de MI RECLAMACIÓN?", "es"))
        self.assertTrue(is_case_continuation("Quero ACOMPANHAR MINHA RECLAMAÇÃO", "pt"))

    def test_validates_inputs_without_echoing_the_request(self):
        for text, language, code in (
            (None, "es", "invalid_request"),
            (17, "pt", "invalid_request"),
            ("   ", "es", "invalid_request"),
            ("a" * 1001, "pt", "request_too_long"),
            ("Quiero retomar mi caso", "en", "unsupported_language"),
            ("Quero retomar meu caso", None, "unsupported_language"),
        ):
            with self.subTest(language=language, code=code):
                with self.assertRaisesRegex(RoutingError, "^" + code + "$"):
                    is_case_continuation(text, language)


if __name__ == "__main__":
    unittest.main()
