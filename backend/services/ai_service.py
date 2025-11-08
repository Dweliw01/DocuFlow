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
            selected_fields: Optional list of DocuWare field names to extract (if provided, uses dynamic extraction)

        Returns:
            Tuple of (DocumentCategory, confidence_score, extracted_data)
            Example: (DocumentCategory.INVOICE, 0.95, ExtractedData(...))
        """
        if selected_fields:
            # Use dynamic field extraction based on DocuWare fields
            prompt = self._build_dynamic_extraction_prompt(text, filename, selected_fields)
        else:
            # Use default extraction
            prompt = self._build_categorization_prompt(text, filename)

        try:
            response = await self._categorize_claude(prompt)
            if selected_fields:
                return self._parse_dynamic_extraction_response(response, selected_fields)
            else:
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

    def _build_dynamic_extraction_prompt(self, text: str, filename: str, selected_fields: list) -> str:
        """
        Build a dynamic prompt that extracts specific DocuWare fields.

        Args:
            text: Document text
            filename: Original filename
            selected_fields: List of DocuWare field names to extract

        Returns:
            Prompt string for Claude
        """
        # Truncate text if too long
        max_chars = 4000
        if len(text) > max_chars:
            text = text[:max_chars] + "...[truncated]"

        categories_list = ", ".join([cat.value for cat in DocumentCategory])
        fields_list = ", ".join(selected_fields)

        return f"""You are a document classification and data extraction expert. Analyze the following document, categorize it, and extract specific fields.

FILENAME: {filename}

DOCUMENT TEXT:
{text}

INSTRUCTIONS:
1. Categorize this document into ONE of the following categories:
   {categories_list}

2. Provide a confidence score between 0.0 and 1.0

3. Extract the following SPECIFIC FIELDS from the document:
   {fields_list}

4. For each field:
   - Look for the information that best matches the field name
   - If the field name suggests a date (e.g., ORDER_DATE, DUE_DATE, SHIP_DATE), extract in YYYY-MM-DD format
   - If the field suggests an amount (e.g., AMOUNT, TOTAL, PRICE), include currency symbol
   - If the field is not present in the document, set it to null
   - Extract EXACTLY what appears on the document, don't invent data

5. Field name hints:
   - VENDOR/SUPPLIER/COMPANY: Who is providing the goods/services
   - CLIENT/CUSTOMER: Who is receiving the goods/services
   - ORDER_DATE/INVOICE_DATE/DATE: Primary document date
   - DUE_DATE/PAYMENT_DATE: When payment is due
   - AMOUNT/TOTAL: Total monetary amount
   - PO_NUMBER/REFERENCE/ORDER_NO: Purchase order or reference number
   - INVOICE_NO/DOC_NUMBER: Document identifier
   - SHIP_DATE/DELIVERY_DATE: Shipping or delivery date
   - TERMS/PAYMENT_TERMS: Payment terms (e.g., "Net 30")

6. ADDITIONALLY, for invoices/receipts: Extract ALL line items with:
   - description: Product/service description
   - quantity: Quantity ordered
   - unit_price: Price per unit
   - amount: Line total

7. Respond ONLY with valid JSON in this exact format (no other text):
{{
    "category": "Category Name",
    "confidence": 0.95,
    "extracted_fields": {{
        "FIELD_NAME_1": "extracted value 1",
        "FIELD_NAME_2": "extracted value 2",
        "FIELD_NAME_3": null
    }},
    "line_items": [
        {{
            "description": "Product Name",
            "quantity": "10",
            "unit_price": "$25.00",
            "amount": "$250.00"
        }}
    ]
}}

DO NOT include markdown code blocks or any other formatting. Output only the JSON object."""

    def _parse_dynamic_extraction_response(self, response: str, selected_fields: list) -> Tuple[DocumentCategory, float, Optional[ExtractedData]]:
        """
        Parse Claude's dynamic extraction response.

        Args:
            response: JSON string from Claude
            selected_fields: List of field names that were requested

        Returns:
            Tuple of (DocumentCategory, confidence_score, extracted_data)
        """
        try:
            # Clean up response
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join([line for line in lines if not line.startswith("```")])

            data = json.loads(response)

            # Extract category
            category_str = data.get("category", "Other")
            category = self._match_category(category_str)

            # Extract confidence
            confidence = float(data.get("confidence", 0.5))

            # Extract fields and map to ExtractedData structure
            extracted_fields = data.get("extracted_fields", {})
            line_items_raw = data.get("line_items", [])

            # Map common DocuWare field names to ExtractedData fields for preview
            # BUT ALSO keep them in other_data with original field names for DocuWare upload
            mapped_data = {}
            other_data = extracted_fields.copy()  # Keep all original fields for DocuWare

            for field_name, value in extracted_fields.items():
                field_upper = field_name.upper()

                # Map vendor/supplier fields
                if any(x in field_upper for x in ['VENDOR', 'SUPPLIER']):
                    mapped_data['vendor'] = value
                # Map client/customer fields
                elif any(x in field_upper for x in ['CLIENT', 'CUSTOMER']):
                    mapped_data['client'] = value
                # Map amount fields
                elif any(x in field_upper for x in ['AMOUNT', 'TOTAL']):
                    mapped_data['amount'] = value
                # Map invoice number fields
                elif any(x in field_upper for x in ['INVOICE_NO', 'INVOICE_NUMBER', 'INV_NO']):
                    mapped_data['document_number'] = value
                # Map PO number fields
                elif any(x in field_upper for x in ['PO_NUMBER', 'P_O_NUMBER', 'REFERENCE']):
                    mapped_data['reference_number'] = value
                # Map date fields
                elif any(x in field_upper for x in ['ORDER_DATE', 'INVOICE_DATE', 'DOC_DATE']):
                    mapped_data['date'] = value
                elif 'DUE_DATE' in field_upper:
                    mapped_data['due_date'] = value
                # Map address fields
                elif 'ADDRESS' in field_upper:
                    mapped_data['address'] = value
                # Map email fields
                elif 'EMAIL' in field_upper:
                    mapped_data['email'] = value
                # Map phone fields
                elif 'PHONE' in field_upper:
                    mapped_data['phone'] = value

            # Convert line items to LineItem objects if present
            line_items = None
            if line_items_raw and isinstance(line_items_raw, list):
                try:
                    from models import LineItem
                    line_items = [LineItem(**item) for item in line_items_raw]
                except Exception as e:
                    print(f"Failed to parse line items: {e}")

            # Create ExtractedData with:
            # - Mapped fields for preview display
            # - other_data with ALL fields in DocuWare field names for upload
            # - line_items for preview
            mapped_data['line_items'] = line_items
            extracted_data = ExtractedData(**mapped_data, other_data=other_data)

            return category, confidence, extracted_data

        except Exception as e:
            print(f"Failed to parse dynamic extraction response: {e}")
            print(f"Response was: {response}")
            # Return safe fallback
            return DocumentCategory.OTHER, 0.3, None
