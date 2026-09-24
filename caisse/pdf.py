"""
caisse/pdf.py

Générateur PDF médico-légal pour le Manifeste de Décaissement & Bon de Sortie de Caisse.
Document officiel matérialisant l'autorisation de la Direction et la décharge du caissier.
"""
import io
import os
from decimal import Decimal
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
)


def generer_manifeste_decaissement_pdf(demande, request=None) -> HttpResponse:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    elements = []
    styles = getSampleStyleSheet()

    # Charte graphique Ets La Lumière
    primary = colors.HexColor('#2A3F54')
    danger = colors.HexColor('#C0392B')
    success = colors.HexColor('#27AE60')
    dark_gray = colors.HexColor('#333333')
    light_bg = colors.HexColor('#F8F9FA')

    style_company = ParagraphStyle(
        'CompanyHeader',
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=15,
        textColor=primary,
    )
    style_sub = ParagraphStyle(
        'CompanySub',
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=dark_gray,
    )
    style_title = ParagraphStyle(
        'DocTitle',
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=17,
        textColor=primary,
        alignment=1,
    )
    style_normal = ParagraphStyle(
        'NormalText',
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=dark_gray,
    )
    style_bold = ParagraphStyle(
        'BoldText',
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=dark_gray,
    )
    style_center = ParagraphStyle(
        'CenterText',
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        alignment=1,
        textColor=dark_gray,
    )

    # 1. En-tête entreprise
    logo_path = os.path.join(settings.MEDIA_ROOT, 'logo', 'logo_ets_la_lumiere.jpg')
    has_logo = os.path.exists(logo_path)

    company_info = [
        Paragraph("<b>ETS LA LUMIÈRE</b>", style_company),
        Paragraph("RCCM : CD/LSH/RCCM/17-A-6183 | Numéro Impôt : A2033591K", style_sub),
        Paragraph("788A, Boulevard M'siri, Q. Industriel, C. Kampemba, Lubumbashi, RDC", style_sub),
        Paragraph("E-mail : info@etslalumiere.cd / adolphechristopher@gmail.com", style_sub),
    ]

    if has_logo:
        try:
            img = RLImage(logo_path, width=2.8 * cm, height=2.2 * cm)
            header_table = Table([[img, company_info]], colWidths=[3.2 * cm, 14.8 * cm])
        except Exception:
            header_table = Table([[company_info]], colWidths=[18.0 * cm])
    else:
        header_table = Table([[company_info]], colWidths=[18.0 * cm])

    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3 * cm))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=primary, spaceAfter=10))

    # 2. Titre du document
    titre_text = f"<b>MANIFESTE DE DÉCAISSEMENT & BON DE SORTIE N° DEC-{demande.pk:05d}</b>"
    elements.append(Paragraph(titre_text, style_title))
    elements.append(Spacer(1, 0.4 * cm))

    # Statut badge & montant
    statut_label = demande.get_statut_display()
    statut_color = success if demande.statut in (demande.APPROUVEE, demande.EXECUTEE) else danger

    style_statut = ParagraphStyle(
        'StatutStyle',
        fontName='Helvetica-Bold',
        fontSize=11,
        alignment=1,
        textColor=statut_color,
    )
    elements.append(Paragraph(f"STATUT : [{statut_label.upper()}]", style_statut))
    elements.append(Spacer(1, 0.3 * cm))

    # Bloc Montant Approuvé mis en valeur
    montant_final = demande.montant_final
    montant_table_data = [
        [
            Paragraph("<b>MONTANT AUTORISÉ :</b>", style_bold),
            Paragraph(f"<font size=14 color='#2A3F54'><b>{montant_final:,.0f} FC</b></font>", style_bold),
        ],
        [
            Paragraph("Montant initialement demandé :", style_sub),
            Paragraph(f"{demande.montant:,.0f} FC", style_sub),
        ],
    ]
    montant_table = Table(montant_table_data, colWidths=[6.0 * cm, 12.0 * cm])
    montant_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), light_bg),
        ('BOX', (0, 0), (-1, -1), 1, primary),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(montant_table)
    elements.append(Spacer(1, 0.4 * cm))

    # 3. Informations détaillées (Tableau à deux colonnes)
    beneficiaire = "—"
    if demande.fournisseur:
        beneficiaire = f"Fournisseur : {demande.fournisseur.nom}"
    elif demande.client:
        beneficiaire = f"Client : {demande.client.nom}"
    elif demande.agent:
        beneficiaire = f"Agent : {demande.agent.nom} {demande.agent.prenom}"
    elif demande.creancier:
        beneficiaire = f"Créancier : {demande.creancier.nom}"
    elif demande.debiteur:
        beneficiaire = f"Débiteur : {demande.debiteur.nom}"

    infos_data = [
        [
            Paragraph("<b>Caisse débitée :</b>", style_normal),
            Paragraph(f"{demande.caisse.caisse.nom}", style_bold),
            Paragraph("<b>Date de la demande :</b>", style_normal),
            Paragraph(demande.date_demande.strftime("%d/%m/%Y à %H:%M"), style_normal),
        ],
        [
            Paragraph("<b>Caissier demandeur :</b>", style_normal),
            Paragraph(f"{demande.demandeur.get_full_name() or demande.demandeur.username if demande.demandeur else '—'}", style_normal),
            Paragraph("<b>Date de décision :</b>", style_normal),
            Paragraph(demande.date_decision.strftime("%d/%m/%Y à %H:%M") if demande.date_decision else "En attente", style_normal),
        ],
        [
            Paragraph("<b>Rubrique de caisse :</b>", style_normal),
            Paragraph(f"{demande.rubrique.nom}", style_normal),
            Paragraph("<b>Validé par :</b>", style_normal),
            Paragraph(f"{demande.valide_par.get_full_name() or demande.valide_par.username if demande.valide_par else '—'}", style_bold),
        ],
        [
            Paragraph("<b>Sous-rubrique :</b>", style_normal),
            Paragraph(f"{demande.sous_rubrique.nom if demande.sous_rubrique else '—'}", style_normal),
            Paragraph("<b>Exécution concrète :</b>", style_normal),
            Paragraph(
                demande.date_execution.strftime("%d/%m/%Y à %H:%M") if demande.date_execution else "Non encore exécutée",
                style_normal
            ),
        ],
        [
            Paragraph("<b>Bénéficiaire :</b>", style_normal),
            Paragraph(beneficiaire, style_bold),
            Paragraph("<b>Réf. Mouvement lié :</b>", style_normal),
            Paragraph(f"#{demande.mouvement_caisse.pk}" if demande.mouvement_caisse else "—", style_normal),
        ],
        [
            Paragraph("<b>Motif du décaissement :</b>", style_normal),
            Paragraph(demande.motif, style_bold),
            Paragraph("<b>Référence pièce :</b>", style_normal),
            Paragraph(demande.reference or "—", style_normal),
        ],
    ]

    infos_table = Table(infos_data, colWidths=[4.2 * cm, 5.0 * cm, 4.0 * cm, 4.8 * cm])
    infos_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E0E0E0')),
        ('BACKGROUND', (0, 0), (0, -1), light_bg),
        ('BACKGROUND', (2, 0), (2, -1), light_bg),
    ]))
    elements.append(infos_table)
    elements.append(Spacer(1, 0.4 * cm))

    # Note / Commentaire de la Direction
    if demande.commentaire_decision:
        comm_data = [
            [
                Paragraph("<b>COMMENTAIRE / MOTIF DE LA DIRECTION :</b>", style_bold),
            ],
            [
                Paragraph(f"<i>« {demande.commentaire_decision} »</i>", style_normal),
            ]
        ]
        comm_table = Table(comm_data, colWidths=[18.0 * cm])
        comm_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), light_bg),
            ('BOX', (0, 0), (-1, -1), 0.5, primary),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(comm_table)
        elements.append(Spacer(1, 0.4 * cm))

    # 4. Zone d'émargement / Signatures médico-légales (3 colonnes)
    elements.append(Spacer(1, 0.6 * cm))
    elements.append(Paragraph("<b>ÉMARGEMENT & VALIDATION LÉGALE</b>", style_bold))
    elements.append(Spacer(1, 0.2 * cm))

    sig_data = [
        [
            Paragraph("<b>Le Caissier (Exécutant)</b><br/><br/><br/><br/>Date : ..............................<br/>Signature :", style_center),
            Paragraph("<b>La Direction Générale (Visa)</b><br/><br/><br/><br/>Date : ..............................<br/>Signature & Sceau :", style_center),
            Paragraph("<b>Le Bénéficiaire (Décharge)</b><br/><br/><br/><br/>Nom : ..............................<br/>Signature pour acquit :", style_center),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[6.0 * cm, 6.0 * cm, 6.0 * cm])
    sig_table.setStyle(TableStyle([
        ('BOX', (0, 0), (0, 0), 0.5, dark_gray),
        ('BOX', (1, 0), (1, 0), 0.5, dark_gray),
        ('BOX', (2, 0), (2, 0), 0.5, dark_gray),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(sig_table)

    # 5. Footer horodaté
    elements.append(Spacer(1, 0.6 * cm))
    footer_text = f"Document généré le {timezone.now().strftime('%d/%m/%Y à %H:%M:%S')} — Système ESM Ets La Lumière"
    elements.append(Paragraph(f"<font size=7 color='#888888'>{footer_text}</font>", style_center))

    doc.build(elements)
    buffer.seek(0)

    filename = f"Manifeste_Decaissement_DEC_{demande.pk:05d}.pdf"
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response
