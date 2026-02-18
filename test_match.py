
import difflib

properties = [
    '/Users/maheswaranm/Makemystayrealty/properties-photos/AA Epsilon Premium Colive.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/AA Premium Coliving PG.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/AA Sparrow Nest Colive.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/AA Sparrow nest premium co live pg.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Arcade Inn Coliving.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Ashok PG Colive.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Astro living.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/At Homes Permium co living pg.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Avinya colive.jpeg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Chap & dona coliving.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Connect Coliving 2,.jpeg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Connect coliving.jpeg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Cozhy coliving pg.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/dvr colive.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Flechazo co living-PG.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Flock 9 Coliving.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Geet Co-Living.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Gina Artize Bomasandra.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Guest Inn Luxury PG for Gents.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/GVS Coliving Studio Rooms.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Haveli Coliving.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Heaven coliving pg.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/hevenhome.jpeg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/JR LUXURY COLIVING.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/K.N Co-living Pg.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/kings & Queens Coliving.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Kio Colive PG.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/KOINN Coliving PG.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Lakshya Co-Living PG.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Livingnest Falcon coliving.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Mio Colive PG.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Mr & Mrs coliving( Mahadevpura).jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Premium Urban Coliving.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Pro colive .jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/SGR enclave coliving.jpg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/shine premium colive.jpeg',
    '/Users/maheswaranm/Makemystayrealty/properties-photos/Urban living.jpg'
 
]

filename = "dvr colive.jpg"

def normalize(s):
    return s.lower().replace('-', ' ').replace('_', ' ').strip()

def score(fname, prop_name):
    f_norm = normalize(os.path.splitext(fname)[0])
    p_norm = normalize(prop_name)
    
    base_score = difflib.SequenceMatcher(None, f_norm, p_norm).ratio()
    
    # Prefix boost
    f_tokens = f_norm.split()
    p_tokens = p_norm.split()
    
    if f_tokens and p_tokens and f_tokens[0] == p_tokens[0]:
        base_score += 0.3  # Boost by 30% if first word matches
        
    return base_score

import os

print(f"Testing match for '{filename}'")
best_match = None
best_s = 0
for p in properties:
    s = score(filename, p)
    if s > best_s:
        best_s = s
        best_match = p
    # print(f"  {p}: {s:.2f}")

print(f"Winner: {best_match} ({best_s:.2f})")
