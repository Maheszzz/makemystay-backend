
const mockProperty = {"id":104,"property_name":"Orion Coliving","location":"Marathahalli","city":null,"phone":"9999999999","map_link":null,"property_type":"PG","furnishing":"fully_furnished","private_price":null,"single_price":null,"double_price":null,"triple_price":null,"starting_price":13000.0,"listing_type":"rent","is_available":true,"slug":null,"created_at":"2026-03-20T05:42:31","updated_at":"2026-03-29T07:03:12","images":[{"image_url":"https://d1yfdszs9lcm9e.cloudfront.net/uploads/befb43d4-e1e7-4e23-a399-756353ec393b.jpeg","is_primary":true,"sort_order":0,"file_size":null,"id":544,"property_id":104,"content_type":"image/jpeg","mime_validated":true,"created_at":"2026-03-20T05:42:31"}],"average_rating":5.0,"review_count":1,"category":"pg","features":["wifi","power_backup","housekeeping","food","security","cctv","geyser","tv","refrigerator","washing machine","bike parking","terrace","lift","common kitchen","balcony","cupboards","furniture","attached bathroom","work desk","couple friendly"]};

function mapRealtyToProperty(item) {
    console.log("Mapping property:", item.id);
    
    const rawImages = Array.isArray(item.images) ? item.images : [];
    const sortedImages = [...rawImages].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
    
    // This is the line from properties.ts:145
    const dbImages = sortedImages.map(img => img.image_url).filter(Boolean);
    
    console.log("Images mapped successfully:", dbImages.length);

    const featuresList = Array.isArray(item.features) ? item.features : [];
    // Similarity to line 210 in mapping function
    const features = featuresList.length > 0 ? featuresList : [];

    console.log("Features mapped successfully:", features.length);
    
    return { id: item.id, images: dbImages, features };
}

try {
    const result = mapRealtyToProperty(mockProperty);
    console.log("SUCCESS!");
} catch (e) {
    console.error("CRASHED!");
    console.error(e);
}
