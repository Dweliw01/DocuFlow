"""
AI Service for document categorization using Claude.
Analyzes extracted text and assigns documents to appropriate categories.
"""
from anthropic import Anthropic
from typing import Tuple, Optional
import json
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from models import DocumentCategory, ExtractedData
from config import settings


class AIService:
    """
    Service for AI-powered document categorization.
    Uses Claude Haiku for cost-effective, accurate categorization.
    """

    def __init__(self):
        """Initialize the AI service with Claude."""
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model
        print(f"[OK] AI Service initialized with {self.model}")

    async def categorize_document(self, text: str, filename: str, selected_fields: Optional[list] = None) -> Tuple[DocumentCategory, float, Optional[ExtractedData]]:
        """
        Categorize document using AI and extract structured data.

        Args:
            text: Extracted text from the document
            filename: Original filename (provides additional context)
            selected_fields: Optional list of field names for context-aware extraction

        Returns:
            Tuple of (DocumentCategory, confidence_score, extracted_data)
            Example: (DocumentCategory.INVOICE, 0.95, ExtractedData(...))
        """
        # Build context-aware prompt if fields are provided
        if selected_fields:
            cabinet_type = self._detect_cabinet_type(selected_fields)
            prompt = self._build_context_aware_prompt(text, filename, selected_fields, cabinet_type)
        else:
            prompt = self._build_categorization_prompt(text, filename)

        try:
            response = await self._categorize_claude(prompt)
            return self._parse_categorization_response(response)

        except Exception as e:
            print(f"AI categorization failed: {e}")
            # Fallback: return "Other" with low confidence and no extracted data
            return DocumentCategory.OTHER, 0.3, None

    def _build_categorization_prompt(self, text: str, filename: str) -> str:
        """
        Build the categorization prompt for Claude.
        Includes clear instructions for categorization AND structured data extraction.
        """
        # Truncate text if too long (to save on API costs and stay within context limits)
        max_chars = 4000
        if len(text) > max_chars:
            text = text[:max_chars] + "...[truncated]"

        categories_list = ", ".join([cat.value for cat in DocumentCategory])

        return f"""You are a document classification and data extraction expert. Analyze the following document, categorize it, and extract structured data.

FILENAME: {filename}

DOCUMENT TEXT:
{text}

INSTRUCTIONS:
1. Categorize this document into ONE of the following categories:
   {categories_list}

2. Provide a confidence score between 0.0 and 1.0

3. Use these guidelines:
   - Invoice: Bills, payment requests, vendor invoices
   - Contract: Legal agreements, service contracts, NDAs
   - Receipt: Payment receipts, purchase confirmations
   - Legal Document: Court documents, legal notices, regulations
   - HR Document: Employee records, performance reviews, job offers
   - Tax Document: Tax returns, W2s, 1099s, tax assessments
   - Financial Statement: Balance sheets, P&L statements, financial reports
   - Correspondence: Letters, emails, memos, general communication
   - Other: Anything that doesn't fit the above categories

4. Extract ALL available structured data from the document. Look for:
   - document_type: Specific document type (e.g., "Purchase Invoice", "Service Agreement", "Sales Receipt")
   - person_name: Name of any person mentioned prominently (recipient, signatory, employee, etc.)
   - company: Company name (the main company the document is about)
   - vendor: Vendor/supplier name (who is providing goods/services)
   - client: Client/customer name (who is receiving goods/services)
   - date: Primary date (invoice date, contract date, issue date, etc.)
   - due_date: Due date or deadline (if applicable)
   - amount: Total amount with currency symbol (e.g., "$1,234.56" or "€500.00")
   - currency: Currency code if identifiable (USD, EUR, GBP, etc.)
   - document_number: Invoice number, contract number, receipt number, reference number, etc.
   - reference_number: PO number, case number, project number, or other reference
   - address: Any address found on the document
   - email: Email address if present
   - phone: Phone number if present
   - line_items: For invoices/receipts, extract each line item as an array with:
     * description: Product/service description
     * quantity: Quantity ordered
     * unit: Unit of measure (e.g., "EA", "boxes", "hours")
     * unit_price: Price per unit
     * amount: Line total
     * sku: Product/SKU code (if present)
     * tax: Tax for this line (if present)
     * discount: Discount applied (if present)
   - other_data: Any other important information (tax ID, terms, account numbers, etc.) as key-value pairs

5. If a field is not present in the document, set it to null. Only extract data that is explicitly present.

6. For line items, extract ALL items from the document. Be thorough and capture every line item with all available details.

7. Respond ONLY with valid JSON in this exact format (no other text):
{{
    "category": "Category Name",
    "confidence": 0.95,
    "extracted_data": {{
        "document_type": "Specific Type",
        "person_name": "John Doe",
        "company": "Acme Corp",
        "vendor": "Office Supplies Inc",
        "client": "Client Company",
        "date": "2024-01-15",
        "due_date": "2024-02-15",
        "amount": "$1,234.56",
        "currency": "USD",
        "document_number": "INV-2024-001",
        "reference_number": "PO-5678",
        "address": "123 Main St, City, State ZIP",
        "email": "contact@example.com",
        "phone": "+1-555-1234",
        "line_items": [
            {{
                "description": "Product Name or Service",
                "quantity": "10",
                "unit": "EA",
                "unit_price": "$25.00",
                "amount": "$250.00",
                "sku": "SKU-123",
                "tax": "$20.00",
                "discount": null
            }},
            {{
                "description": "Another Item",
                "quantity": "5",
                "unit": "boxes",
                "unit_price": "$15.00",
                "amount": "$75.00",
                "sku": null,
                "tax": null,
                "discount": "$5.00"
            }}
        ],
        "other_data": {{
            "tax_id": "12-3456789",
            "payment_terms": "Net 30"
        }}
    }}
}}

DO NOT include markdown code blocks or any other formatting. Output only the JSON object."""

    async def _categorize_claude(self, prompt: str) -> str:
        """
        Get categorization and data extraction from Claude.
        Uses synchronous API call (Anthropic Python SDK doesn't have async yet).
        """
        message = self.client.messages.create(
            model=self.model,
            max_tokens=2500,  # Increased to handle line items extraction (invoices can have many items)
            temperature=0.1,  # Low temperature for consistent, focused results
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Extract text from response
        return message.content[0].text

    def _parse_categorization_response(self, response: str) -> Tuple[DocumentCategory, float, Optional[ExtractedData]]:
        """
        Parse Claude's response and extract category, confidence, and structured data.
        Handles various response formats gracefully.

        Args:
            response: JSON string from Claude

        Returns:
            Tuple of (DocumentCategory, confidence_score, extracted_data)
        """
        try:
            # Clean up response (remove markdown code blocks if present)
            response = response.strip()
            if response.startswith("```"):
                # Extract JSON from markdown code block
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            response = response.strip()

            # Parse JSON
            data = json.loads(response)

            # Extract category and confidence
            category_str = data.get("category", "Other")
            confidence = float(data.get("confidence", 0.5))

            # Match string to DocumentCategory enum
            category = self._match_category(category_str)

            # Clamp confidence between 0 and 1
            confidence = max(0.0, min(1.0, confidence))

            # Extract structured data
            extracted_data = None
            if "extracted_data" in data and data["extracted_data"]:
                try:
                    extracted_data = ExtractedData(**data["extracted_data"])
                except Exception as e:
                    print(f"Failed to parse extracted_data: {e}")
                    # Continue without extracted data rather than failing completely

            return category, confidence, extracted_data

        except Exception as e:
            print(f"Failed to parse AI response: {e}")
            print(f"Response was: {response}")
            # Return safe fallback
            return DocumentCategory.OTHER, 0.3, None

    def _match_category(self, category_str: str) -> DocumentCategory:
        """
        Match string to DocumentCategory enum.
        Uses exact matching first, then fuzzy matching as fallback.

        Args:
            category_str: Category name from AI response

        Returns:
            Matched DocumentCategory enum value
        """
        category_str = category_str.strip().lower()

        # Try exact match first
        for category in DocumentCategory:
            if category.value.lower() == category_str:
                return category

        # Partial matching as fallback
        if "invoice" in category_str:
            return DocumentCategory.INVOICE
        elif "contract" in category_str:
            return DocumentCategory.CONTRACT
        elif "receipt" in category_str:
            return DocumentCategory.RECEIPT
        elif "legal" in category_str:
            return DocumentCategory.LEGAL
        elif "hr" in category_str or "human resource" in category_str:
            return DocumentCategory.HR
        elif "tax" in category_str:
            return DocumentCategory.TAX
        elif "financial" in category_str:
            return DocumentCategory.FINANCIAL
        elif "correspondence" in category_str or "letter" in category_str:
            return DocumentCategory.CORRESPONDENCE

        # Default to OTHER if no match
        return DocumentCategory.OTHER

    def _detect_cabinet_type(self, selected_fields: list) -> str:
        """
        Detect cabinet type based on selected field names.

        Args:
            selected_fields: List of field names selected by user

        Returns:
            Cabinet type string: 'HR', 'AP', 'AR', 'Sales', 'Legal', 'General'
        """
        # Convert all field names to uppercase for matching
        fields_upper = [field.upper() for field in selected_fields]
        fields_str = ' '.join(fields_upper)

        # HR indicators
        hr_keywords = ['EMPLOYEE', 'HIRE', 'SALARY', 'WAGE', 'DEPARTMENT', 'POSITION',
                       'TITLE', 'MANAGER', 'PERFORMANCE', 'REVIEW', 'TERMINATION',
                       'ONBOARD', 'BENEFIT', 'LEAVE', 'VACATION', 'SICK', 'PTO',
                       'PERSONNEL', 'STAFF', 'WORKER', 'JOB', 'EMPLOYMENT']
        hr_score = sum(1 for keyword in hr_keywords if keyword in fields_str)

        # AP (Accounts Payable) indicators
        ap_keywords = ['VENDOR', 'SUPPLIER', 'INVOICE', 'BILL', 'PAYMENT', 'DUE_DATE',
                       'AMOUNT', 'PO_NUMBER', 'PURCHASE', 'ORDER', 'PAYABLE', 'EXPENSE',
                       'COST', 'TOTAL', 'TAX', 'RECEIPT', 'PAID']
        ap_score = sum(1 for keyword in ap_keywords if keyword in fields_str)

        # AR (Accounts Receivable) indicators
        ar_keywords = ['CUSTOMER', 'CLIENT', 'RECEIVABLE', 'REVENUE', 'SALES',
                       'COLLECTION', 'AGING', 'CREDIT', 'DEBIT']
        ar_score = sum(1 for keyword in ar_keywords if keyword in fields_str)

        # Sales indicators
        sales_keywords = ['DEAL', 'OPPORTUNITY', 'QUOTE', 'PROPOSAL', 'CONTRACT',
                         'COMMISSION', 'TERRITORY', 'PIPELINE', 'FORECAST',
                         'LEAD', 'PROSPECT']
        sales_score = sum(1 for keyword in sales_keywords if keyword in fields_str)

        # Legal indicators
        legal_keywords = ['CONTRACT', 'AGREEMENT', 'LEGAL', 'CLAUSE', 'TERM',
                         'PARTY', 'SIGNATORY', 'JURISDICTION', 'LIABILITY',
                         'INDEMNITY', 'CONFIDENTIAL', 'NDA']
        legal_score = sum(1 for keyword in legal_keywords if keyword in fields_str)

        # Determine cabinet type based on highest score
        scores = {
            'HR': hr_score,
            'AP': ap_score,
            'AR': ar_score,
            'Sales': sales_score,
            'Legal': legal_score
        }

        # Get the type with highest score
        max_score = max(scores.values())
        if max_score >= 2:  # Need at least 2 matching keywords
            cabinet_type = max(scores, key=scores.get)
            print(f"Detected cabinet type: {cabinet_type} (score: {max_score})")
            return cabinet_type

        print("Detected cabinet type: General (no strong indicators)")
        return 'General'

    def _build_context_aware_prompt(self, text: str, filename: str, selected_fields: list, cabinet_type: str) -> str:
        """
        Build a context-aware prompt based on cabinet type and selected fields.

        Args:
            text: Document text
            filename: Original filename
            selected_fields: List of field names to extract
            cabinet_type: Detected cabinet type (HR, AP, AR, Sales, Legal, General)

        Returns:
            Prompt string for Claude
        """
        # Truncate text if too long
        max_chars = 4000
        if len(text) > max_chars:
            text = text[:max_chars] + "...[truncated]"

        categories_list = ", ".join([cat.value for cat in DocumentCategory])
        fields_list = ", ".join(selected_fields)

        # Build context-specific guidance based on cabinet type
        context_guidance = self._get_context_guidance(cabinet_type)

        return f"""You are a document classification and data extraction expert specializing in {cabinet_type} documents. Analyze the following document, categorize it, and extract specific fields.

FILENAME: {filename}

DOCUMENT TEXT:
{text}

CONTEXT: This document is being filed in a {cabinet_type} cabinet. {context_guidance}

INSTRUCTIONS:
1. Categorize this document into ONE of the following categories:
   {categories_list}

2. Provide a confidence score between 0.0 and 1.0

3. Extract ONLY the following fields from the document:
   {fields_list}

4. Extraction guidelines:
   - Extract ONLY the fields listed above - do not extract fields not in this list
   - If a field name suggests a date (e.g., contains DATE), use YYYY-MM-DD format
   - If a field name suggests an amount/number (e.g., AMOUNT, SALARY, TOTAL), extract as plain number with decimals (e.g., "25000.50")
   - If a field is not present in the document, set it to null
   - Extract information exactly as it appears - do not invent or infer data

5. Field interpretation hints (based on {cabinet_type} context):
{self._get_field_hints(cabinet_type)}

6. Respond ONLY with valid JSON in this exact format (no markdown, no other text):
{{
    "category": "Category Name",
    "confidence": 0.95,
    "extracted_data": {{
        "FIELD_NAME_1": "value 1",
        "FIELD_NAME_2": "value 2",
        "FIELD_NAME_3": null
    }}
}}"""

    def _get_context_guidance(self, cabinet_type: str) -> str:
        """Get context-specific guidance for different cabinet types."""
        guidance = {
            'HR': "Focus on employee-related information such as names, departments, positions, dates of employment, and compensation details.",
            'AP': "Focus on vendor information, invoice details, payment amounts, purchase orders, and due dates.",
            'AR': "Focus on customer information, revenue details, payment collection, and aging information.",
            'Sales': "Focus on deal details, client information, contract values, sales representatives, and opportunity data.",
            'Legal': "Focus on contract parties, agreement terms, signatures, dates, and legal obligations.",
            'General': "Extract the requested fields as they appear in the document."
        }
        return guidance.get(cabinet_type, guidance['General'])

    def _get_field_hints(self, cabinet_type: str) -> str:
        """Get field-specific hints based on cabinet type."""
        hints = {
            'HR': """   - EMPLOYEE_ID/EMPLOYEE_NO: Unique employee identifier
   - HIRE_DATE/START_DATE: Date when employee started
   - DEPARTMENT: Organizational department or division
   - POSITION/TITLE: Job title or role
   - SALARY/WAGE: Compensation amount (extract number only)
   - MANAGER: Name of direct supervisor
   - TERMINATION_DATE/END_DATE: Last day of employment (if applicable)""",

            'AP': """   - VENDOR/SUPPLIER: Company providing goods/services
   - INVOICE_NO/INVOICE_NUMBER: Unique invoice identifier
   - INVOICE_DATE: Date invoice was issued
   - DUE_DATE/PAYMENT_DATE: When payment is due
   - AMOUNT/TOTAL: Total amount (extract number only)
   - PO_NUMBER/PURCHASE_ORDER: Purchase order reference
   - TAX: Tax amount (extract number only)""",

            'AR': """   - CUSTOMER/CLIENT: Company or person receiving goods/services
   - INVOICE_NO: Invoice or billing reference
   - INVOICE_DATE: Date of invoice
   - AMOUNT/TOTAL: Amount due (extract number only)
   - DUE_DATE: Payment due date
   - AGING: Days past due (if applicable)""",

            'Sales': """   - CLIENT/CUSTOMER: Prospective or current customer
   - DEAL_VALUE/CONTRACT_VALUE: Total deal amount (extract number only)
   - SALES_REP: Sales representative name
   - CLOSE_DATE: Expected or actual close date
   - STAGE: Sales pipeline stage
   - OPPORTUNITY_ID: Unique opportunity identifier""",

            'Legal': """   - CONTRACT_NO/AGREEMENT_NO: Unique contract identifier
   - PARTY_1/PARTY_2: Contracting parties
   - EFFECTIVE_DATE: When contract takes effect
   - EXPIRATION_DATE: When contract ends
   - CONTRACT_VALUE: Total contract value (extract number only)
   - SIGNATORY: Person authorized to sign""",

            'General': """   - Extract each field as it most naturally appears in the document
   - Use field names as hints for what type of information to look for
   - Dates should be in YYYY-MM-DD format
   - Numbers should be plain decimals without currency symbols"""
        }
        return hints.get(cabinet_type, hints['General'])
